"""Content API (Doc 02): the V1 flow through HTTP, fail-closed at every step."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.assets import Asset
from packages.domain.enums import RightsClassification
from packages.domain.models import Profile, Source, Workspace
from packages.research.opportunity import OpportunityService
from packages.research.rights import RightsService
from packages.research.verification import KnowledgeService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"capi-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _seed_full(db, world):
    """workspace + profile + opportunity with supported claim, verified asset,
    platform plan — ready to produce content."""
    from packages.domain.editorial import PlatformPlan

    ws, profile = world
    ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
    opps = OpportunityService(db)
    knowledge = KnowledgeService(db)
    rights = RightsService(db)

    opp = opps.create(ctx, title="Bondinho de 1911", why_profile="memória urbana")
    claim = knowledge.add_claim(ctx, subject="Bondinho", predicate="iniciou em", object="1911")
    src = Source(
        workspace_id=ws.id, profile_id=profile.id,
        url=f"https://arquivo-{uuid.uuid4().hex[:6]}.test/a", source_type="rss",
    )
    db.add(src)
    db.flush()
    knowledge.add_evidence(ctx, claim_id=claim.id, supports=True, source_id=src.id)
    asset = Asset(
        workspace_id=ws.id, profile_id=profile.id,
        asset_type="PHOTO", file_hash=uuid.uuid4().hex, status="ACTIVE",
    )
    db.add(asset)
    db.flush()
    record = rights.classify(
        ctx, asset_id=asset.id, classification=RightsClassification.PUBLIC_DOMAIN
    )
    rights.verify(ctx, record)
    opps.attach(ctx, opp, claim_ids=[claim.id], asset_ids=[asset.id])
    db.add(
        PlatformPlan(
            workspace_id=ws.id, opportunity_id=opp.id, platform="instagram", method="MANUAL"
        )
    )
    db.commit()  # later endpoints share the same session; keep objects fresh
    db.expire_all()
    return opp.id, claim.id


def test_full_content_flow_through_api(client, db, world):
    opp_id, claim_id = _seed_full(db, world)
    detail = client.get(
        f"/api/v1/opportunities/{opp_id}?workspace_id={world[0].id}"
    )
    assert detail.status_code == 200
    assert detail.json()["claims"][0]["id"] == str(claim_id)
    assert "Bondinho" in detail.json()["claims"][0]["text"]

    created = client.post(
        f"/api/v1/opportunities/{opp_id}/create-content?workspace_id={world[0].id}",
        json={"format": "PHOTO_POST", "editorial_angle": "memória", "seo_entities": ["bondinho"]},
    )
    assert created.status_code == 200
    package_id = created.json()["package_id"]

    draft = client.post(
        f"/api/v1/content/{package_id}/generate-draft?workspace_id={world[0].id}",
        json={"title": "1911", "caption": "O bondinho...", "claim_ids_used": [str(claim_id)]},
    )
    assert draft.status_code == 200

    qc = client.post(f"/api/v1/content/{package_id}/run-qc?workspace_id={world[0].id}")
    assert qc.status_code == 200
    body = qc.json()
    assert body["gates"]["evidence"] == "PASS"
    assert body["gates"]["rights"] == "PASS"
    assert body["gates"]["human_review"] == "REQUIRED"

    approved = client.post(f"/api/v1/content/{package_id}/approve?workspace_id={world[0].id}")
    assert approved.status_code == 200
    assert approved.json()["state"] == "READY"

    exported = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={world[0].id}",
        json={"platform": "instagram"},
    )
    assert exported.status_code == 200
    assert "post-" in exported.json()["export_path"]


def test_export_blocked_before_approval_returns_409(client, db, world):
    opp_id, claim_id = _seed_full(db, world)
    created = client.post(
        f"/api/v1/opportunities/{opp_id}/create-content?workspace_id={world[0].id}",
        json={"format": "PHOTO_POST", "seo_entities": ["x"]},
    )
    package_id = created.json()["package_id"]
    client.post(
        f"/api/v1/content/{package_id}/generate-draft?workspace_id={world[0].id}",
        json={"title": "T", "caption": "C", "claim_ids_used": [str(claim_id)]},
    )
    client.post(f"/api/v1/content/{package_id}/run-qc?workspace_id={world[0].id}")
    blocked = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={world[0].id}",
        json={"platform": "instagram"},
    )
    assert blocked.status_code == 409


def test_unknown_format_rejected(client, db, world):
    opp_id, _ = _seed_full(db, world)
    resp = client.post(
        f"/api/v1/opportunities/{opp_id}/create-content?workspace_id={world[0].id}",
        json={"format": "LONG_VIDEO"},
    )
    assert resp.status_code == 422
