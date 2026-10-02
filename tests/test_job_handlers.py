"""Integration tests for the worker handler registry (``build_handlers``).

Two behaviours are pinned here:

- STUB handlers (no payload requirements) must succeed on an empty payload;
- REAL handlers (Doc 17 wiring) validate the payload and FAIL CLOSED on an
  empty one (FatalJobError -> FAILED), never reporting success without work.
"""

from types import SimpleNamespace
from uuid import uuid4

from apps.worker.__main__ import build_handlers
from apps.worker.engine import JOB_FAILED, JOB_SUCCEEDED, JobEngine
from packages.domain.enums import JobType

# Real handlers that REQUIRE domain ids in the payload; an empty payload is a
# schema error and must fail closed (Doc 03 non-retryable). OPPORTUNITY_ANALYSIS
# (opportunity_ids optional) and LEARNING_ANALYSIS (no payload needed) accept
# an empty payload on purpose.
REAL_HANDLERS_REQUIRING_IDS = {
    "DISCOVERY_SCAN",
    "SOURCE_RETRIEVAL",
    "CLAIM_VERIFICATION",
    "IMAGE_ANALYSIS",
    "RIGHTS_RESEARCH",
    "CLAIM_EXTRACTION",
    "FORMAT_PLANNING",
    "QC",
    "EXPORT",
    "ANALYTICS_SYNC",
    "COMMENT_SYNC",
    "CONTENT_GENERATION",
    "ADVERSARIAL_RESEARCH",
}
REAL_HANDLERS = REAL_HANDLERS_REQUIRING_IDS | {
    "OPPORTUNITY_ANALYSIS",
    "LEARNING_ANALYSIS",
}


class DummySession:
    """Minimal stand-in: JobEngine needs flush/commit/add (append_audit)."""

    def __init__(self):
        self.commits = 0

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def add(self, obj):
        pass

    def get(self, model, key):
        return None


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


def test_registry_covers_every_job_type():
    """Every JobType enum value has a registered handler (Doc 03 contract)."""
    handlers = build_handlers()
    for jt in JobType:
        assert jt.value in handlers, f"{jt.value} has no registered handler"


def test_stub_handlers_succeed_on_empty_payload():
    handlers = build_handlers()
    engine = JobEngine(DummySession(), handlers)
    for jt in JobType:
        if jt.value in REAL_HANDLERS:
            continue
        job = make_job(jt.value)
        result = engine.run_job(job)
        assert result.status == JOB_SUCCEEDED, f"{jt.value} failed: {job.error}"
        assert result.checkpoint["completed_steps"], f"{jt.value} missing checkpoint"


def test_real_handlers_fail_closed_on_empty_payload():
    """Empty payload is a schema error: FAILED, audited, never SUCCEEDED."""
    handlers = build_handlers()
    engine = JobEngine(DummySession(), handlers)
    for jt in sorted(REAL_HANDLERS_REQUIRING_IDS):
        job = make_job(jt)
        result = engine.run_job(job)
        assert result.status == JOB_FAILED, f"{jt} unexpectedly succeeded"
        assert result.error, f"{jt} failed without an error message"


def test_qc_handler_scopes_by_workspace():
    """A QC job for a package id that does not exist in the job's workspace
    fails closed with a scoping error — never touches foreign data (Doc 08)."""
    handlers = build_handlers()
    engine = JobEngine(DummySession(), handlers)
    job = make_job("QC")
    job.payload = {"package_id": str(uuid4())}
    result = engine.run_job(job)
    assert result.status == JOB_FAILED
    assert "not found in job workspace" in (result.error or "")
