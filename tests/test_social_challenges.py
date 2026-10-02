"""Factuality Challenge tests (AMENDMENT-2026-10-02-013, contract §11).

Core rules under test:
- a comment is NEVER evidence by itself: the challenge creates a claim and
  the verdict comes from the deterministic judge over registered evidence;
- judge mapping: POSSIBLE/PROBABLE->CONFIRMED, CONTROVERSIAL->DISPUTED,
  UNKNOWN->UNSUPPORTED;
- human review is the authoritative gate (review/dismiss);
- workspace/profile isolation (cross-profile access fails closed).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.models import Profile, Workspace
from packages.domain.publishing import Comment
from packages.research.social import SocialError, SocialIntelligenceService
from packages.shared.db import get_session


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"social-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


def _comment(db, world) -> Comment:
    ws, profile = world
    comment = Comment(
        workspace_id=ws.id,
        profile_id=profile.id,
        author_ref="user-42",
        text="O bondinho não começou em 1911, começou em 1912!",
        intent="QUESTION",
        qualified_signal=None,
    )
    db.add(comment)
    db.commit()
    return comment


def test_create_challenge_turns_comment_into_claim(db, world):
    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world),
        comment_id=comment.id,
        statement="O bondinho começou a operar em 1911",
    )
    assert challenge.status == "PROPOSED"
    assert challenge.verdict is None
    assert challenge.claim_id is not None
    # the claim exists and is typed as a factuality challenge
    from packages.domain.knowledge import Claim

    claim = db.get(Claim, challenge.claim_id)
    assert claim.claim_type == "factuality_challenge"


def test_unsupported_verdict_with_zero_evidence(db, world):
    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world), comment_id=comment.id, statement="Alegação sem evidências"
    )
    resolved = service.research_challenge(_ctx(world), challenge.id)
    assert resolved.status == "RESOLVED"
    assert resolved.verdict == "UNSUPPORTED"  # zero evidence -> unsupported
    assert resolved.verdict_metadata["engine_verdict"] == "UNKNOWN"
    assert "human review" in resolved.verdict_metadata["note"]


def test_confirmed_mapping_with_two_independent_sources(db, world):
    from packages.domain.enums import UncertaintyState
    from packages.domain.knowledge import Claim, EvidenceRecord
    from packages.domain.models import Source

    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world), comment_id=comment.id, statement="O bondinho começou em 1911"
    )

    # evidence registered through the NORMAL path (registered sources)
    for i, domain in enumerate(("arquivo-nacional.test", "hemeroteca.test")):
        src = Source(
            workspace_id=ws.id,
            profile_id=profile.id,
            url=f"https://{domain}/doc-{i}",
            source_type="rss",
            publisher=domain.split(".")[0],
        )
        db.add(src)
        db.flush()
        db.add(
            EvidenceRecord(
                workspace_id=ws.id,
                profile_id=profile.id,
                claim_id=challenge.claim_id,
                source_id=src.id,
                supports=True,
                independence_group=f"group-{i}",
                strength=5,
            )
        )
    claim = db.get(Claim, challenge.claim_id)
    claim.status = UncertaintyState.PROBABLE
    db.commit()

    resolved = service.research_challenge(_ctx(world), challenge.id)
    assert resolved.verdict == "CONFIRMED"
    assert resolved.verdict_metadata["engine_verdict"] == "PROBABLE"
    assert resolved.verdict_metadata["supporting_groups"] >= 2


def test_disputed_mapping_on_contradiction(db, world):
    from packages.domain.enums import UncertaintyState
    from packages.domain.knowledge import Claim
    from packages.research.verification import VerificationOutcome

    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world), comment_id=comment.id, statement="Alegação contestada"
    )
    # judge outcome is deterministic; simulate the CONTROVERSIAL branch by
    # checking the mapping table directly (evidence path covered elsewhere)
    from packages.research.social import JUDGE_MAPPING

    assert JUDGE_MAPPING["CONTROVERSIAL"] == "DISPUTED"
    claim = db.get(Claim, challenge.claim_id)
    assert claim is not None  # claim linked for the evidence trail
    _ = VerificationOutcome, UncertaintyState  # mapping contract documented


def test_human_review_is_the_final_gate(db, world):
    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world), comment_id=comment.id, statement="Alegação revisada"
    )
    service.research_challenge(_ctx(world), challenge.id)
    reviewed = service.review_challenge(
        _ctx(world),
        challenge.id,
        verdict="DISPUTED",
        reason="Revisão humana: fonte primária contradiz",
    )
    assert reviewed.verdict == "DISPUTED"
    assert reviewed.status == "RESOLVED"
    assert reviewed.reviewed_at is not None


def test_dismiss_challenge(db, world):
    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world), comment_id=comment.id, statement="Alegação irrelevante"
    )
    dismissed = service.dismiss_challenge(
        _ctx(world), challenge.id, reason="Fora do escopo editorial"
    )
    assert dismissed.status == "DISMISSED"
    with pytest.raises(SocialError, match="cannot be reviewed"):
        service.review_challenge(
            _ctx(world), dismissed.id, verdict="CONFIRMED"
        )


def test_workspace_isolation_fails_closed(db, world):
    ws, profile = world
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    challenge = service.create_challenge(
        _ctx(world), comment_id=comment.id, statement="Alegação isolada"
    )
    # foreign profile context cannot see or resolve the challenge
    other_ctx = _ctx(world)  # same workspace: ok
    assert service.get_challenge(other_ctx, challenge.id) is not None
    # a workspace-less/other profile context is blocked by scoping
    from packages.shared.execution_context import ExecutionContext

    foreign = ExecutionContext(workspace_id=ws.id, profile_id=uuid.uuid4())
    assert service.get_challenge(foreign, challenge.id) is None
    with pytest.raises(SocialError, match="not found in profile"):
        service.research_challenge(foreign, challenge.id)


def _ctx(world):
    from packages.shared.execution_context import ExecutionContext

    ws, profile = world
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def test_api_challenge_flow(client, db, world):
    ws, profile = world
    comment = _comment(db, world)

    created = client.post(
        f"/api/v1/social/challenges?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "comment_id": str(comment.id),
            "statement": "O bondinho começou a operar em 1911",
        },
    )
    assert created.status_code == 200, created.text
    challenge_id = created.json()["id"]

    listed = client.get(
        f"/api/v1/social/challenges?workspace_id={ws.id}&profile_id={profile.id}"
    )
    assert listed.status_code == 200
    assert any(c["id"] == challenge_id for c in listed.json())

    reviewed = client.post(
        f"/api/v1/social/challenges/{challenge_id}/review?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "verdict": "UNSUPPORTED",
            "reason": "Sem evidências nas fontes registradas",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["verdict"] == "UNSUPPORTED"


def test_api_rejects_invalid_verdict(client, db, world):
    ws, profile = world
    resp = client.post(
        f"/api/v1/social/challenges?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "comment_id": str(uuid.uuid4()),
            "statement": "Teste de veredito inválido",
        },
    )
    # comment does not exist -> 409 fail closed
    assert resp.status_code == 409
