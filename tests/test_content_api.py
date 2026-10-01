"""Content API (Doc 02): the V1 flow through HTTP, fail-closed at every step."""

import hashlib
import uuid
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apps.api.main import app
from packages.domain.assets import Asset
from packages.domain.editorial import OpportunityAsset
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


def test_full_content_flow_through_api(client, db, world, monkeypatch, tmp_path):
    from apps.api import content_routes
    from packages.shared.settings import Settings

    export_root = tmp_path / "exports"
    temp_root = tmp_path / "temp"
    asset_root = tmp_path / "assets"
    monkeypatch.setattr(
        content_routes,
        "get_settings",
        lambda: Settings(
            export_root=str(export_root),
            temp_root=str(temp_root),
            asset_root=str(asset_root),
        ),
    )
    opp_id, claim_id = _seed_full(db, world)
    asset_link = db.query(OpportunityAsset).filter_by(opportunity_id=opp_id).one()
    asset = db.get(Asset, asset_link.ref_id)
    # a real decodable PNG: export now renders stills from included assets
    buffer = BytesIO()
    Image.new("RGB", (320, 400), (120, 90, 60)).save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
    asset.storage_path = f"originals/{asset.id}.png"
    asset.file_hash = hashlib.sha256(image_bytes).hexdigest()
    image_path = asset_root / asset.storage_path
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(image_bytes)
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
    detail = client.get(
        f"/api/v1/opportunities/{opp_id}?workspace_id={world[0].id}"
    )
    assert detail.json()["content_package_id"] == package_id

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

    restored = client.get(
        f"/api/v1/content/{package_id}?workspace_id={world[0].id}"
    )
    assert restored.status_code == 200
    restored_body = restored.json()
    assert restored_body["drafts"][-1]["title"] == "1911"
    assert restored_body["drafts"][-1]["caption"] == "O bondinho..."
    assert restored_body["drafts"][-1]["claim_ids_used"] == [str(claim_id)]
    assert restored_body["latest_qc"]["status"] == body["status"]
    assert restored_body["latest_qc"]["is_current"] is True

    foreign_workspace = Workspace(name=f"other-{uuid.uuid4().hex[:8]}")
    db.add(foreign_workspace)
    db.flush()
    foreign = client.get(
        f"/api/v1/content/{package_id}?workspace_id={foreign_workspace.id}"
    )
    assert foreign.status_code == 404

    approved = client.post(f"/api/v1/content/{package_id}/approve?workspace_id={world[0].id}")
    assert approved.status_code == 200
    assert approved.json()["state"] == "READY"

    exported = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={world[0].id}",
        json={"platform": "instagram"},
    )
    assert exported.status_code == 200
    assert "post-" in exported.json()["export_path"]
    downloaded = client.get(
        f"/api/v1/content/{package_id}/export/download?workspace_id={world[0].id}"
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(downloaded.content)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "captions/caption.txt" in archive.namelist()
        assert "1911" in archive.read("captions/caption.txt").decode("utf-8")
        assert archive.read(f"image/{asset.id}.png") == image_bytes
        assert f"rights/{asset.id}.json" in archive.namelist()
        assert "sources/claims-and-evidence.json" in archive.namelist()
        assert len([name for name in archive.namelist() if name.startswith("sources/")]) == 2
    assert list(temp_root.iterdir()) == []


def test_download_export_refuses_revoked_approval(client, db, world, monkeypatch, tmp_path):
    from apps.api import content_routes
    from packages.domain.editorial import Opportunity
    from packages.shared.settings import Settings

    monkeypatch.setattr(
        content_routes,
        "get_settings",
        lambda: Settings(
            export_root=str(tmp_path / "exports"),
            temp_root=str(tmp_path / "temp"),
        ),
    )
    opp_id, claim_id = _seed_full(db, world)
    created = client.post(
        f"/api/v1/opportunities/{opp_id}/create-content?workspace_id={world[0].id}",
        json={"format": "PHOTO_POST", "seo_entities": ["bondinho"]},
    )
    package_id = created.json()["package_id"]
    client.post(
        f"/api/v1/content/{package_id}/generate-draft?workspace_id={world[0].id}",
        json={"title": "1911", "caption": "O bondinho", "claim_ids_used": [str(claim_id)]},
    )
    client.post(f"/api/v1/content/{package_id}/run-qc?workspace_id={world[0].id}")
    client.post(f"/api/v1/content/{package_id}/approve?workspace_id={world[0].id}")
    exported = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={world[0].id}",
        json={"platform": "instagram"},
    )
    assert exported.status_code == 200

    opportunity = db.get(Opportunity, opp_id)
    opportunity.state = "REJECTED"
    db.flush()
    downloaded = client.get(
        f"/api/v1/content/{package_id}/export/download?workspace_id={world[0].id}"
    )
    assert downloaded.status_code == 409


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


def test_draft_rejects_claim_from_another_workspace(client, db, world):
    opp_id, _ = _seed_full(db, world)
    created = client.post(
        f"/api/v1/opportunities/{opp_id}/create-content?workspace_id={world[0].id}",
        json={"format": "PHOTO_POST"},
    )
    package_id = created.json()["package_id"]

    other_workspace = Workspace(name=f"foreign-{uuid.uuid4().hex[:8]}")
    db.add(other_workspace)
    db.flush()
    other_profile = Profile(
        workspace_id=other_workspace.id,
        key="foreign",
        name="Foreign",
    )
    db.add(other_profile)
    db.flush()
    foreign_claim = KnowledgeService(db).add_claim(
        ExecutionContext(
            workspace_id=other_workspace.id,
            profile_id=other_profile.id,
        ),
        subject="Foreign",
        predicate="is",
        object="separate",
    )

    second_profile = Profile(
        workspace_id=world[0].id,
        key="another-profile",
        name="Another profile",
    )
    db.add(second_profile)
    db.flush()
    foreign_profile_claim = KnowledgeService(db).add_claim(
        ExecutionContext(
            workspace_id=world[0].id,
            profile_id=second_profile.id,
        ),
        subject="Other profile",
        predicate="is",
        object="separate",
    )

    for claim in (foreign_claim, foreign_profile_claim):
        response = client.post(
            f"/api/v1/content/{package_id}/generate-draft?workspace_id={world[0].id}",
            json={
                "title": "Invalid citation",
                "caption": "Claim from another scope",
                "claim_ids_used": [str(claim.id)],
            },
        )
        assert response.status_code == 422
        assert "belong to the opportunity" in response.text
