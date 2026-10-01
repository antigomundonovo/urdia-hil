"""Integration tests for the real job handlers.

These tests exercise the handlers with a dummy in‑memory job engine.
"""

from uuid import uuid4
from types import SimpleNamespace

from apps.worker.engine import JobEngine, JOB_SUCCEEDED
from apps.worker.__main__ import build_handlers


class DummySession:
    def __init__(self):
        self.commits = 0

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def scalars(self, stmt):
        # Return empty list for simplicity
        return []

    def get(self, model, key):
        return None

    def add(self, obj):
        pass

    def scalar(self, stmt):
        return None

    def close(self):
        pass


def make_job(jt: str):
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        profile_id=uuid4(),
        job_type=jt,
        payload={},
        checkpoint={"completed_steps": [], "next_step": None},
        status="RUNNING",
        attempt=1,
        max_attempts=1,
        result=None,
        finished_at=None,
        error=None,
    )


def test_real_handlers_accept_job():
    handlers = build_handlers()
    session = DummySession()
    engine = JobEngine(session, handlers)
    for jt in ["IMAGE_ANALYSIS", "RIGHTS_RESEARCH", "CLAIM_EXTRACTION", "FORMAT_PLANNING", "OPPORTUNITY_ANALYSIS"]:
        job = make_job(jt)
        # The handlers will fail with FatalJobError because payload is empty;
        # we just want to check they are reachable.
        try:
            engine.run_job(job)
        except Exception:
            # Expected failures due to missing payload – handlers are reachable.
            pass
        assert job.status in ("SUCCEEDED", "FAILED"), f"{jt} not run"
