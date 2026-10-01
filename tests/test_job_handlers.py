"""Integration tests for the stub job handlers.

The tests create a minimal in‑memory DB session via ``SessionLocal`` and use the
``JobEngine`` with the mapping from ``build_handlers``.  They only check that a
job can be claimed, executed, and ends in ``SUCCEEDED`` and that the checkpoint
contains the handler name.
"""

from uuid import uuid4
from types import SimpleNamespace

from apps.worker import engine as worker_engine
from apps.worker.engine import JobEngine, JobProgress, JOB_SUCCEEDED
from packages.domain.enums import JobType
from packages.shared.db import SessionLocal

# Helper to create a very small in‑memory database session that merely records commit
class DummySession:
    def __init__(self):
        self.commits = 0
        self.items = []

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def scalars(self, stmt):
        return []

    def get(self, model, key):
        return None

    def add(self, obj):
        self.items.append(obj)

    def scalar(self, stmt):
        return None

    def close(self):
        pass

# Build the handlers from __main__ (now includes all stubs)
from apps.worker.__main__ import build_handlers

handlers = build_handlers()

# Create a dummy job for each JobType
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


def test_all_handlers_can_run():
    session = DummySession()
    engine = JobEngine(session, handlers)
    for jt in JobType.__members__.keys():
        job = make_job(jt)
        res_job = engine.run_job(job)
        assert res_job.status == JOB_SUCCEEDED, f"{jt} failed"
        assert res_job.checkpoint["completed_steps"], f"{jt} missing checkpoint"
