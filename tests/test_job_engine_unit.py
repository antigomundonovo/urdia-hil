"""Database-independent tests for worker retry classification."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from apps.worker import engine as worker_engine
from apps.worker.engine import JOB_FAILED, JOB_PENDING, JobEngine, RetryableJobError


class _Session:
    def __init__(self):
        self.commit_calls = 0

    def flush(self):
        pass

    def commit(self):
        self.commit_calls += 1

    def get(self, model, job_id):
        return self.job


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


def test_recovery_audits_running_to_pending_transition(monkeypatch):
    audit_events = []
    monkeypatch.setattr(
        worker_engine,
        "append_audit",
        lambda _session, **event: audit_events.append(event),
    )
    job = _job()
    job.status = worker_engine.JOB_RUNNING
    session = _Session()
    session.scalars = lambda statement: [job]

    recovered = JobEngine(session, {}).recover_running()

    assert recovered == 1
    assert job.status == JOB_PENDING
    assert audit_events[0]["action"] == "JOB_RECOVERED"
    assert audit_events[0]["previous_state"] == worker_engine.JOB_RUNNING
    assert audit_events[0]["new_state"] == JOB_PENDING


def test_retry_and_cancel_audit_status_changes(monkeypatch):
    audit_events = []
    monkeypatch.setattr(
        worker_engine,
        "append_audit",
        lambda _session, **event: audit_events.append(event),
    )
    job = _job()
    job.status = JOB_FAILED
    session = _Session()
    session.job = job
    engine = JobEngine(session, {})

    assert engine.retry_failed(job.id, job.workspace_id) is job
    assert audit_events[-1]["action"] == "JOB_RETRY_REQUESTED"
    assert audit_events[-1]["previous_state"] == JOB_FAILED
    assert audit_events[-1]["new_state"] == JOB_PENDING

    assert engine.cancel(job.id, job.workspace_id) is job
    assert audit_events[-1]["action"] == "JOB_CANCELLED"
    assert audit_events[-1]["previous_state"] == JOB_PENDING
    assert audit_events[-1]["new_state"] == worker_engine.JOB_CANCELLED


def test_progress_checkpoints_commit_immediately(monkeypatch):
    monkeypatch.setattr(worker_engine, "append_audit", lambda *args, **kwargs: None)
    session = _Session()
    job = _job()

    def handler(ctx, payload, progress):
        progress.done("fetch")
        assert session.commit_calls == 1
        progress.next("extract")
        assert session.commit_calls == 2
        return {"ok": True}

    JobEngine(session, {"DISCOVERY_SCAN": handler}).run_job(job)

    assert job.checkpoint == {"completed_steps": ["fetch"], "next_step": "extract"}
    assert job.status == "SUCCEEDED"
    assert session.commit_calls == 2
