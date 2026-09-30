"""Database-independent tests for worker retry classification."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from apps.worker import engine as worker_engine
from apps.worker.engine import JOB_FAILED, JOB_PENDING, JobEngine, RetryableJobError


class _Session:
    def flush(self):
        pass


def _job():
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        profile_id=uuid4(),
        job_type="DISCOVERY_SCAN",
        payload={},
        checkpoint={"completed_steps": [], "next_step": None},
        status="RUNNING",
        attempt=1,
        max_attempts=3,
        result=None,
        finished_at=None,
        error=None,
    )


def test_unclassified_failure_fails_without_retry(monkeypatch):
    monkeypatch.setattr(worker_engine, "append_audit", lambda *args, **kwargs: None)

    def handler(ctx, payload, progress):
        raise ValueError("invalid payload")

    job = _job()
    JobEngine(_Session(), {"DISCOVERY_SCAN": handler}).run_job(job)

    assert job.status == JOB_FAILED
    assert "unclassified ValueError" in job.error
    assert isinstance(job.finished_at, datetime)
    assert job.finished_at.tzinfo is UTC


def test_retryable_failure_is_requeued(monkeypatch):
    monkeypatch.setattr(worker_engine, "append_audit", lambda *args, **kwargs: None)

    def handler(ctx, payload, progress):
        raise RetryableJobError("temporary network failure")

    job = _job()
    JobEngine(_Session(), {"DISCOVERY_SCAN": handler}).run_job(job)

    assert job.status == JOB_PENDING
    assert job.error == "temporary network failure"
