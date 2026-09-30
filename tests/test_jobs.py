"""Job engine tests (Doc 16 non-negotiable: restart recovery, provider
failure classes, retry ceilings, isolation, audit on terminal states)."""

import uuid

import pytest

from apps.worker.engine import (
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    FatalJobError,
    JobEngine,
    RetryableJobError,
    record_job_step,
)
from packages.domain.enums import JobType
from packages.domain.models import Job, Profile, Workspace
from packages.domain.repositories import AuditRepository, JobRepository


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"jobs-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _make_job(
    db,
    ws,
    profile,
    job_type=JobType.DISCOVERY_SCAN,
    payload=None,
    max_attempts=None,
    **kwargs,
):
    job = Job(
        workspace_id=ws.id,
        profile_id=profile.id,
        job_type=job_type,
        payload=payload or {},
        max_attempts=max_attempts,
        **kwargs,
    )
    db.add(job)
    db.flush()
    return job


def test_success_flow_with_checkpoints(db, world):
    ws, profile = world
    calls = []

    def handler(ctx, payload, progress):
        if "fetch" not in progress.completed:
            calls.append("fetch")
            progress.done("fetch")
            progress.next("extract")
        if "extract" not in progress.completed:
            calls.append("extract")
            progress.done("extract")

    job = _make_job(db, ws, profile)
    engine = JobEngine(db, {str(job.job_type): handler})
    engine.claim_next()
    engine.run_job(job)

    assert job.status == JOB_SUCCEEDED
    assert job.attempt == 1
    assert calls == ["fetch", "extract"]
    assert job.checkpoint["completed_steps"] == ["fetch", "extract"]
    assert job.result == {}


def test_restart_recovery_resumes_from_checkpoint(db, world):
    """Doc 16 non-negotiable: worker killed mid-job → checkpoint resume."""
    ws, profile = world
    executed = []

    def handler(ctx, payload, progress):
        if "fetch" not in progress.completed:
            executed.append("fetch")
            progress.done("fetch")
            progress.next("analyze")
        if "analyze" not in progress.completed:
            executed.append("analyze")
            progress.done("analyze")

    # first run "crashes" after fetch (simulated: RUNNING job with checkpoint)
    job = _make_job(
        db,
        ws,
        profile,
        status=JOB_RUNNING,
        checkpoint={"completed_steps": ["fetch"], "next_step": "analyze"},
        attempt=1,
    )
    db.flush()

    # "restart": new engine, recover RUNNING jobs, re-run
    engine = JobEngine(db, {str(job.job_type): handler})
    assert engine.recover_running() == 1
    assert job.status == JOB_PENDING
    claimed = engine.claim_next()
    assert claimed is job
    engine.run_job(job)

    assert job.status == JOB_SUCCEEDED
    assert executed == ["analyze"]  # fetch NOT re-executed
    assert job.checkpoint["completed_steps"] == ["fetch", "analyze"]


def test_retryable_failure_is_requeued_then_succeeds(db, world):
    ws, profile = world
    state = {"tries": 0}

    def flaky(ctx, payload, progress):
        state["tries"] += 1
        if state["tries"] == 1:
            raise RetryableJobError("temporary network error")
        progress.done("fetch")
        return {"ok": True}

    job = _make_job(db, ws, profile, max_attempts=3)
    engine = JobEngine(db, {str(job.job_type): flaky})

    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_PENDING  # requeued
    assert job.attempt == 1
    assert "temporary network" in job.error

    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_SUCCEEDED
    assert job.attempt == 2
    assert state["tries"] == 2


def test_fatal_failure_never_retries(db, world):
    ws, profile = world

    def fatal(ctx, payload, progress):
        raise FatalJobError("invalid schema: rights block")

    job = _make_job(db, ws, profile, max_attempts=5)
    engine = JobEngine(db, {str(job.job_type): fatal})
    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_FAILED
    assert job.attempt == 1  # no second attempt
    assert "rights block" in job.error


def test_retry_ceiling_fails_job(db, world):
    ws, profile = world

    def always_transient(ctx, payload, progress):
        raise RetryableJobError("rate limited")

    job = _make_job(db, ws, profile, max_attempts=2)
    engine = JobEngine(db, {str(job.job_type): always_transient})
    for _ in range(3):
        claimed = engine.claim_next()
        if claimed is None:
            break
        engine.run_job(claimed)
    assert job.status == JOB_FAILED
    assert job.attempt == 2  # ceiling respected


def test_unknown_handler_fails_without_retry(db, world):
    ws, profile = world
    job = _make_job(db, ws, profile, job_type=JobType.LEARNING_ANALYSIS)
    engine = JobEngine(db, {})  # no handlers
    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_FAILED
    assert "no handler" in job.error


def test_job_isolation_scoped_fetch(db, world):
    ws, profile = world
    job = _make_job(db, ws, profile)
    repo = JobRepository(db)
    assert repo.get_scoped(job.id, ws.id) is job
    assert repo.get_scoped(job.id, uuid.uuid4()) is None


def test_terminal_states_are_audited(db, world):
    ws, profile = world

    def ok(ctx, payload, progress):
        return {"done": True}

    job = _make_job(db, ws, profile)
    engine = JobEngine(db, {str(job.job_type): ok})
    engine.claim_next()
    engine.run_job(job)

    events = [
        e for e in AuditRepository(db).list_for_workspace(ws.id) if e.action == "JOB_COMPLETED"
    ]
    assert len(events) == 1
    assert events[0].entity_id == job.id


def test_retry_endpoint_flow_via_repo_and_engine(db, world):
    ws, profile = world

    def fatal(ctx, payload, progress):
        raise FatalJobError("policy block")

    job = _make_job(db, ws, profile)
    engine = JobEngine(db, {str(job.job_type): fatal})
    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_FAILED

    retried = engine.retry_failed(job.id, ws.id)
    assert retried.status == JOB_PENDING
    # foreign workspace cannot retry (fail closed)
    assert engine.retry_failed(job.id, uuid.uuid4()) is None


def test_record_job_step_writes_row(db, world):
    from sqlalchemy import select

    from packages.domain.models import JobStep

    ws, profile = world
    job = _make_job(db, ws, profile)
    record_job_step(db, job, "fetch")
    row = db.scalar(select(JobStep).where(JobStep.job_id == job.id, JobStep.step == "fetch"))
    assert row is not None
    assert row.status == "DONE"
