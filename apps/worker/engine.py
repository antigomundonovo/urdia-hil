"""Job engine (Doc 17 step 13; Doc 03 jobs/checkpoints/retry; Doc 07 recovery).

Rules implemented here, all spec-mandated:
- checkpoint JSON per Doc 03: {"completed_steps": [...], "next_step": "..."}
  persisted after each step so a killed worker resumes, never restarting
  completed steps (Doc 07: on restart inspect RUNNING jobs, checkpoint
  recovery, never silently delete job history);
- retry only the retryable classes (Doc 03): timeout, temporary network,
  provider unavailable, rate limit, temporary service. Handlers raise
  FatalJobError for the non-retryable classes (invalid schema, bad
  credentials, rights block, policy block, fact-check failure) — no infinite
  retries;
- max_attempts is a hard ceiling; exceeding it fails the job;
- job lifecycle terminal states are audited (append-only).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.enums import JobType
from packages.domain.models import Job, JobStep
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

# Job lifecycle statuses (Doc 07 requires recognizing RUNNING for recovery)
JOB_PENDING = "PENDING"
JOB_RUNNING = "RUNNING"
JOB_SUCCEEDED = "SUCCEEDED"
JOB_FAILED = "FAILED"
JOB_CANCELLED = "CANCELLED"

DEFAULT_MAX_ATTEMPTS = 3


class FatalJobError(Exception):
    """Non-retryable per Doc 03: invalid schema, bad credentials, rights
    block, policy block, fact-check failure."""


class RetryableJobError(Exception):
    """Transient per Doc 03: timeout, network, provider unavailable, rate limit."""


Handler = Callable[[ExecutionContext, dict[str, Any], "JobProgress"], dict[str, Any] | None]


class JobProgress:
    """Handler-facing checkpoint helper; mutations persist through the engine."""

    def __init__(
        self,
        completed: list[str],
        next_step: str | None,
        on_change: Callable[[dict[str, Any]], None],
    ):
        self.completed: list[str] = completed
        self.next_step: str | None = next_step
        self._on_change = on_change

    def done(self, step: str) -> None:
        if step not in self.completed:
            self.completed.append(step)
        self._persist()

    def next(self, step: str) -> None:
        self.next_step = step
        self._persist()

    def _persist(self) -> None:
        self._on_change(self.snapshot())

    def snapshot(self) -> dict[str, Any]:
        return {"completed_steps": list(self.completed), "next_step": self.next_step}


class JobEngine:
    def __init__(
        self,
        session: Session,
        handlers: dict[str, Handler],
        default_max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self.session = session
        self.handlers = handlers
        self.default_max_attempts = default_max_attempts

    # --- lifecycle --------------------------------------------------------

    def claim_next(self) -> Job | None:
        """Atomically claim one PENDING job (multi-worker safe)."""
        job = self.session.scalars(
            select(Job)
            .where(Job.status == JOB_PENDING)
            .order_by(Job.priority.desc().nullslast(), Job.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        max_attempts = job.max_attempts or self.default_max_attempts
        attempt = (job.attempt or 0) + 1
        if attempt > max_attempts:
            self._fail(job, f"max attempts exhausted ({max_attempts})")
            return None
        job.status = JOB_RUNNING
        job.attempt = attempt
        job.started_at = datetime.now(UTC)
        if job.checkpoint is None:
            job.checkpoint = {"completed_steps": [], "next_step": None}
        self.session.flush()
        return job

    def run_job(self, job: Job) -> Job:
        ctx = ExecutionContext(
            workspace_id=job.workspace_id,
            profile_id=job.profile_id,
            job_id=job.id,
            correlation_id=f"job:{job.id}",
        )

        def persist(snapshot: dict[str, Any]) -> None:
            job.checkpoint = snapshot
            self.session.flush()

        progress = JobProgress(
            completed=list((job.checkpoint or {}).get("completed_steps", [])),
            next_step=(job.checkpoint or {}).get("next_step"),
            on_change=persist,
        )

        handler = self.handlers.get(str(job.job_type))
        if handler is None:
            self._fail(job, f"no handler registered for job_type={job.job_type}")
            return job

        try:
            result = handler(ctx, dict(job.payload or {}), progress)
            job.status = JOB_SUCCEEDED
            job.result = result or {}
            job.finished_at = datetime.now(UTC)
            job.error = None
            append_audit(
                self.session,
                ctx=ctx,
                action="JOB_COMPLETED",
                entity_type="job",
                entity_id=job.id,
                new_state=JOB_SUCCEEDED,
                metadata={"job_type": str(job.job_type), "attempt": job.attempt},
            )
        except FatalJobError as exc:
            self._fail(job, str(exc), ctx=ctx)
        except RetryableJobError as exc:
            max_attempts = job.max_attempts or self.default_max_attempts
            if (job.attempt or 1) >= max_attempts:
                self._fail(
                    job,
                    f"attempt {job.attempt}/{max_attempts} failed: {exc}",
                    ctx=ctx,
                )
            else:
                # transient failure → requeue with checkpoint preserved (Doc 03)
                job.status = JOB_PENDING
                job.error = str(exc)
                append_audit(
                    self.session,
                    ctx=ctx,
                    action="JOB_REQUEUED",
                    entity_type="job",
                    entity_id=job.id,
                    new_state=JOB_PENDING,
                    reason=str(exc),
                    metadata={"attempt": job.attempt},
                )
        except Exception as exc:
            # Unclassified failures fail closed; only explicitly transient
            # conditions may consume a retry.
            self._fail(
                job,
                f"unclassified {exc.__class__.__name__}: {exc}",
                ctx=ctx,
            )
        self.session.flush()
        return job

    def recover_running(self) -> int:
        """Doc 07: on restart, inspect RUNNING jobs and requeue them with their
        checkpoints; history is never deleted."""
        stuck = list(self.session.scalars(select(Job).where(Job.status == JOB_RUNNING)))
        count = 0
        for job in stuck:
            job.status = JOB_PENDING
            count += 1
        if count:
            self.session.flush()
        return count

    def retry_failed(self, job_id: UUID, workspace_id: UUID) -> Job | None:
        job = self.session.get(Job, job_id)
        if job is None or job.workspace_id != workspace_id:
            return None  # fail closed on foreign workspace
        if job.status != JOB_FAILED:
            return None
        job.status = JOB_PENDING
        job.error = None
        self.session.flush()
        return job

    def cancel(self, job_id: UUID, workspace_id: UUID) -> Job | None:
        job = self.session.get(Job, job_id)
        if job is None or job.workspace_id != workspace_id:
            return None
        if job.status in (JOB_SUCCEEDED, JOB_CANCELLED):
            return None
        job.status = JOB_CANCELLED
        job.finished_at = datetime.now(UTC)
        self.session.flush()
        return job

    # --- helpers ----------------------------------------------------------

    def _fail(self, job: Job, error: str, ctx: ExecutionContext | None = None) -> None:
        job.status = JOB_FAILED
        job.error = error
        job.finished_at = datetime.now(UTC)
        if ctx is not None:
            append_audit(
                self.session,
                ctx=ctx,
                action="JOB_FAILED",
                entity_type="job",
                entity_id=job.id,
                new_state=JOB_FAILED,
                reason=error,
                metadata={"job_type": str(job.job_type), "attempt": job.attempt},
            )
        self.session.flush()


def record_job_step(session: Session, job: Job, step: str, status: str = "DONE") -> None:
    session.add(JobStep(job_id=job.id, step=step, status=status))
    session.flush()


JOB_TYPE_VALUES = [jt.value for jt in JobType]
