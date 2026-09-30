"""Knowledge layer tests — Doc 16 must-pass rules applied to claims/evidence."""

import uuid

import pytest
from sqlalchemy import select

from packages.domain.enums import UncertaintyState
from packages.domain.knowledge import Claim, Contradiction, Verdict
from packages.domain.models import Profile, Source, Workspace
from packages.domain.repositories import AuditRepository
from packages.research.verification import KnowledgeService
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"know-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _ctx(ws, profile):
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _source(db, world) -> Source:
    ws, profile = world
    src = Source(
        workspace_id=ws.id, profile_id=profile.id,
        url=f"https://fonte-{uuid.uuid4().hex[:8]}.test/doc",
        source_type="rss",
    )
    db.add(src)
    db.flush()
    return src


def _claim(db, world) -> Claim:
    ws, profile = world
    return KnowledgeService(db).add_claim(
        _ctx(ws, profile),
        subject="Praça XV",
        predicate="foi inaugurada em",
        object="1784",
        claim_type="fact",
    )


def test_new_claim_starts_unknown_and_not_ready(db, world):
    """Doc 16: claim without evidence → NOT_READY."""
    ws, profile = world
    claim = _claim(db, world)
    assert claim.status is UncertaintyState.UNKNOWN
    service = KnowledgeService(db)
    assert not service.claims_pipeline_ready([claim.id])


def test_single_independent_support_is_possible(db, world):
    ws, profile = world
    claim = _claim(db, world)
    service = KnowledgeService(db)
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=True,
        source_id=_source(db, world).id, evidence_type="document",
    )
    assert claim.status is UncertaintyState.POSSIBLE
    assert service.claims_pipeline_ready([claim.id]) is not None  # has support now
    assert service.claims_pipeline_ready([claim.id]) is True


def test_copy_is_not_independence(db, world):
    """Doc 00 §28: não tratar cópia como independência — two records from the
    SAME source/group stay POSSIBLE, never PROBABLE."""
    ws, profile = world
    claim = _claim(db, world)
    service = KnowledgeService(db)
    same_source = _source(db, world)
    for _ in range(3):
        service.add_evidence(
            _ctx(ws, profile), claim_id=claim.id, supports=True,
            source_id=same_source.id, evidence_type="article",
        )
    assert claim.status is UncertaintyState.POSSIBLE


def test_two_independent_groups_is_probable(db, world):
    ws, profile = world
    claim = _claim(db, world)
    service = KnowledgeService(db)
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=True,
        source_id=_source(db, world).id, independence_group="arquivo-nacional",
    )
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=True,
        source_id=_source(db, world).id, independence_group="biblioteca-nacional",
    )
    assert claim.status is UncertaintyState.PROBABLE


def test_contradiction_preserves_both_sides(db, world):
    """Doc 16: independent contradictory sources → CONTROVERSIAL, both kept."""
    ws, profile = world
    claim = _claim(db, world)
    service = KnowledgeService(db)
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=True,
        source_id=_source(db, world).id, independence_group="a",
    )
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=False,
        source_id=_source(db, world).id, independence_group="b",
        excerpt="datas divergentes",
    )
    assert claim.status is UncertaintyState.CONTROVERSIAL
    contradiction = db.scalar(select(Contradiction).where(Contradiction.claim_id == claim.id))
    assert contradiction is not None
    assert len(contradiction.supporting_side) == 1
    assert len(contradiction.contradicting_side) == 1
    assert contradiction.status == "OPEN"


def test_confirmed_and_refuted_never_awarded_deterministically(db, world):
    ws, profile = world
    claim = _claim(db, world)
    service = KnowledgeService(db)
    for i in range(5):
        service.add_evidence(
            _ctx(ws, profile), claim_id=claim.id, supports=True,
            source_id=_source(db, world).id, independence_group=f"g{i}",
        )
    assert claim.status is UncertaintyState.PROBABLE  # ceiling of the engine


def test_verdict_history_is_appended_not_rewritten(db, world):
    ws, profile = world
    claim = _claim(db, world)
    service = KnowledgeService(db)
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=True, source_id=_source(db, world).id
    )
    service.add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=False,
        source_id=_source(db, world).id, independence_group="b",
    )
    verdicts = list(db.scalars(select(Verdict).where(Verdict.claim_id == claim.id)))
    assert [v.verdict for v in verdicts] == [
        UncertaintyState.POSSIBLE,
        UncertaintyState.CONTROVERSIAL,
    ]  # full history preserved


def test_evidence_for_foreign_workspace_fails_closed(db, world):
    ws, profile = world
    claim = _claim(db, world)
    foreign_ctx = ExecutionContext(workspace_id=uuid.uuid4(), profile_id=uuid.uuid4())
    with pytest.raises(LookupError):
        KnowledgeService(db).add_evidence(foreign_ctx, claim_id=claim.id, supports=True)


def test_claim_events_are_audited(db, world):
    ws, profile = world
    claim = _claim(db, world)
    KnowledgeService(db).add_evidence(
        _ctx(ws, profile), claim_id=claim.id, supports=True, source_id=_source(db, world).id
    )
    actions = {e.action for e in AuditRepository(db).list_for_workspace(ws.id)}
    assert {"CLAIM_CREATED", "EVIDENCE_ADDED", "CLAIM_VERIFIED"} <= actions


def test_verification_job_updates_claims(db, world):
    """CLAIM_VERIFICATION handler runs through the real job engine."""
    from apps.worker.engine import JOB_SUCCEEDED, JobEngine
    from apps.worker.handlers import claim_verification
    from packages.domain.enums import JobType
    from packages.domain.models import Job

    ws, profile = world
    claim = _claim(db, world)
    job = Job(
        workspace_id=ws.id,
        profile_id=profile.id,
        job_type=JobType.CLAIM_VERIFICATION,
        priority=999,  # claim ahead of stale PENDING jobs from previous runs
        payload={"workspace_id": str(ws.id), "profile_id": str(profile.id)},
    )
    db.add(job)
    db.commit()  # handler opens its own session and must see committed data

    engine = JobEngine(db, {"CLAIM_VERIFICATION": claim_verification})
    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_SUCCEEDED
    assert job.result["verified"] >= 1
    assert claim.status is UncertaintyState.UNKNOWN  # still no evidence
