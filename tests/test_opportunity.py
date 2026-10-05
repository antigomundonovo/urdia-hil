"""Opportunity + JEV tests (Doc 12 decisions, Doc 16 gates, Doc 03 machine)."""

import uuid

import pytest

from packages.domain.assets import Asset
from packages.domain.editorial import OpportunityClaim, OpportunitySource
from packages.domain.enums import (
    JEVDecision,
    OpportunityState,
    RightsClassification,
)
from packages.domain.knowledge import Story
from packages.domain.models import Profile, Source, Workspace
from packages.research.opportunity import OpportunityService
from packages.research.rights import RightsService
from packages.research.verification import KnowledgeService
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"jev-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile, OpportunityService(db), KnowledgeService(db), RightsService(db)


def _ctx(ws, profile):
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _source(db, world) -> Source:
    ws, profile = world[0], world[1]
    src = Source(
        workspace_id=ws.id, profile_id=profile.id,
        url=f"https://f-{uuid.uuid4().hex[:6]}.test/x", source_type="rss",
    )
    db.add(src)
    db.flush()
    return src


def _asset(db, world) -> Asset:
    ws, profile = world[0], world[1]
    a = Asset(
        workspace_id=ws.id, profile_id=profile.id,
        asset_type="PHOTO", file_hash=uuid.uuid4().hex, status="ACTIVE",
    )
    db.add(a)
    db.flush()
    return a


def _supported_claim(db, world, ctx) -> uuid.UUID:
    ws, profile, _, knowledge, _ = world
    claim = knowledge.add_claim(ctx, subject="S", predicate="p", object="o")
    knowledge.add_evidence(ctx, claim_id=claim.id, supports=True, source_id=_source(db, world).id)
    return claim.id


def test_opportunity_enters_machine_at_candidate(db, world):
    ws, profile, opps, *_ = world
    opp = opps.create(_ctx(ws, profile), title="A chegada do trem")
    assert opp.state == OpportunityState.CANDIDATE.value
    # the machine's next step from CANDIDATE is RESEARCHING — audited, legal
    opps.transition(_ctx(ws, profile), opp, OpportunityState.RESEARCHING, reason="normalized")


def test_jev_needs_research_when_claims_lack_evidence(db, world):
    """Doc 16: claim without evidence → the JEV cannot PROCEED."""
    ws, profile, opps, knowledge, _ = world
    ctx = _ctx(ws, profile)
    claim = knowledge.add_claim(ctx, subject="S", predicate="p", object="o")  # no evidence
    opp = opps.create(ctx, title="História X")
    opps.attach(ctx, opp, claim_ids=[claim.id])

    rec = opps.jev_recommend(ctx, opp)
    assert rec.decision is JEVDecision.NEEDS_RESEARCH
    assert rec.requires_human_review is True

    opps.jev_decide(ctx, opp, JEVDecision.NEEDS_RESEARCH)
    assert opp.state == OpportunityState.NEEDS_RESEARCH.value
    assert opp.decision == JEVDecision.NEEDS_RESEARCH.value


def test_jev_proceeds_with_supported_claims(db, world):
    ws, profile, opps, knowledge, _ = world
    ctx = _ctx(ws, profile)
    claim_id = _supported_claim(db, world, ctx)
    opp = opps.create(ctx, title="História Y", why_now="aniversário de 100 anos")
    opps.attach(ctx, opp, claim_ids=[claim_id])

    rec = opps.jev_recommend(ctx, opp)
    assert rec.decision is JEVDecision.PROCEED

    opps.jev_decide(ctx, opp, JEVDecision.PROCEED)
    assert opp.state == OpportunityState.RESEARCHING.value


def test_jev_quarantines_on_blocking_rights(db, world):
    """Doc 11/16: rights gate fail → QUARANTINE."""
    ws, profile, opps, knowledge, rights = world
    ctx = _ctx(ws, profile)
    claim_id = _supported_claim(db, world, ctx)
    asset = _asset(db, world)  # no rights record = UNKNOWN = BLOCK
    opp = opps.create(ctx, title="História Z")
    opps.attach(ctx, opp, claim_ids=[claim_id], asset_ids=[asset.id])

    rec = opps.jev_recommend(ctx, opp)
    assert rec.decision is JEVDecision.QUARANTINE

    opps.jev_decide(ctx, opp, JEVDecision.QUARANTINE)
    assert opp.state == OpportunityState.QUARANTINED.value


def test_jev_proceeds_when_rights_verified(db, world):
    ws, profile, opps, knowledge, rights = world
    ctx = _ctx(ws, profile)
    claim_id = _supported_claim(db, world, ctx)
    asset = _asset(db, world)
    record = rights.classify(
        ctx, asset_id=asset.id, classification=RightsClassification.PUBLIC_DOMAIN
    )
    rights.verify(ctx, record)
    opp = opps.create(ctx, title="História W")
    opps.attach(ctx, opp, claim_ids=[claim_id], asset_ids=[asset.id])

    assert opps.jev_recommend(ctx, opp).decision is JEVDecision.PROCEED


def test_jev_flags_controversial_high_priority(db, world):
    ws, profile, opps, knowledge, _ = world
    ctx = _ctx(ws, profile)
    claim = knowledge.add_claim(ctx, subject="S", predicate="p", object="o")
    knowledge.add_evidence(ctx, claim_id=claim.id, supports=True, source_id=_source(db, world).id)
    knowledge.add_evidence(
        ctx, claim_id=claim.id, supports=False,
        source_id=_source(db, world).id, independence_group="other",
    )
    opp = opps.create(ctx, title="História conflituosa")
    opps.attach(ctx, opp, claim_ids=[claim.id])

    rec = opps.jev_recommend(ctx, opp)
    assert rec.decision is JEVDecision.PROCEED
    assert rec.priority == "HIGH"
    assert opps.transition is not None  # machine remains under TransitionService


def test_reject_parks_opportunity_and_blocks_shortcuts(db, world):
    ws, profile, opps, *_ = world
    ctx = _ctx(ws, profile)
    opp = opps.create(ctx, title="Fora do perfil")
    opps.jev_decide(ctx, opp, JEVDecision.REJECT, reason="outside profile")
    assert opp.state == OpportunityState.REJECTED.value
    from packages.domain.state_machine import TransitionError

    with pytest.raises(TransitionError):
        opps.transition(ctx, opp, OpportunityState.RESEARCHING)  # no shortcut back


def test_opportunity_isolation_scoped_fetch(db, world):
    ws, profile, opps, *_ = world
    opp = opps.create(_ctx(ws, profile), title="Privado")
    assert opps.get_scoped(opp.id, ws.id) is not None
    assert opps.get_scoped(opp.id, uuid.uuid4()) is None
    assert opps.list_for_profile(ws.id, profile.id)
    assert not opps.list_for_profile(ws.id, uuid.uuid4())


def test_opportunity_rejects_references_from_another_profile(db, world):
    ws, profile, opps, knowledge, _ = world
    ctx = _ctx(ws, profile)
    opp = opps.create(ctx, title="Scoped opportunity")
    other_profile = Profile(workspace_id=ws.id, key="foreign", name="Foreign")
    db.add(other_profile)
    db.flush()
    foreign_ctx = _ctx(ws, other_profile)
    foreign_claim = knowledge.add_claim(
        foreign_ctx,
        subject="Private",
        predicate="is",
        object="foreign",
    )
    foreign_source = Source(
        workspace_id=ws.id,
        profile_id=other_profile.id,
        url="https://foreign.test/source",
        source_type="rss",
    )
    foreign_asset = Asset(
        workspace_id=ws.id,
        profile_id=other_profile.id,
        asset_type="PHOTO",
        status="ACTIVE",
    )
    db.add_all([foreign_source, foreign_asset])
    db.flush()

    with pytest.raises(LookupError, match="claim not found"):
        opps.attach(ctx, opp, claim_ids=[foreign_claim.id])
    with pytest.raises(LookupError, match="source not found"):
        opps.attach(ctx, opp, source_ids=[foreign_source.id])
    with pytest.raises(LookupError, match="asset not found"):
        opps.attach(ctx, opp, asset_ids=[foreign_asset.id])
    with pytest.raises(LookupError, match="opportunity not found"):
        opps.attach(foreign_ctx, opp, claim_ids=[])
    with pytest.raises(LookupError, match="opportunity not found"):
        opps.jev_recommend(foreign_ctx, opp)

    assert db.query(OpportunityClaim).filter_by(opportunity_id=opp.id).count() == 0
    assert db.query(OpportunitySource).filter_by(opportunity_id=opp.id).count() == 0


def test_opportunity_rejects_story_from_another_profile(db, world):
    ws, profile, opps, _, _ = world
    other_profile = Profile(workspace_id=ws.id, key="story-profile", name="Other")
    db.add(other_profile)
    db.flush()
    story = Story(
        workspace_id=ws.id,
        profile_id=other_profile.id,
        title="Private story",
    )
    db.add(story)
    db.flush()

    with pytest.raises(LookupError, match="story not found"):
        opps.create(_ctx(ws, profile), title="Invalid", story_id=story.id)
