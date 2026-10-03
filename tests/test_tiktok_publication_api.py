"""TikTok publication API integration tests with the provider mocked."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from packages.domain.editorial import CanonicalContent, ContentPackage, Draft, Opportunity
from packages.domain.models import AuditEvent, Profile, User, Workspace, WorkspaceMember
from apps.api.auth import get_current_user
from packages.domain.publishing import Publication
from packages.providers import tiktok as tiktok_module
from packages.shared.db import get_session


def _world(db):
    ws = Workspace(name=f"tt-{uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    opp = Opportunity(workspace_id=ws.id, profile_id=profile.id, title="TikTok")
    db.add(opp)
    db.flush()
    canonical = CanonicalContent(
        workspace_id=ws.id,
        opportunity_id=opp.id,
        key_message="mensagem",
    )
    db.add(canonical)
    db.flush()
    package = ContentPackage(
        workspace_id=ws.id,
        opportunity_id=opp.id,
        canonical_content_id=canonical.id,
        format="VIDEO",
    )
    db.add(package)
    db.flush()
    db.add(
        Draft(
            workspace_id=ws.id,
            content_package_id=package.id,
            title="Vídeo URDIA",
            caption="Legenda de teste.",
        )
    )
    pub = Publication(
        workspace_id=ws.id,
        profile_id=profile.id,
        content_package_id=package.id,
        platform="tiktok",
        method="EXPORT",
        status="PENDING",
        idempotency_key=f"{profile.id}:{package.id}:tiktok:v1",
    )
    db.add(pub)
    db.commit()
    actor = User(
        name="TikTok Publisher",
        email=f"tiktok-publisher-{uuid4().hex[:8]}@example.test",
    )
    db.add(actor)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=actor.id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: actor
    db.expire_all()
    return ws, profile, pub


def test_tiktok_publish_submits_processing(client, db, monkeypatch):
    ws, profile, pub = _world(db)
    submitted = {}

    class FakePublisher:
        def publish(self, payload, *, idempotency_key):
            submitted.update(payload)
            submitted["idempotency_key"] = idempotency_key
            return SimpleNamespace(publish_id="pub-123")

    monkeypatch.setattr(tiktok_module, "TikTokPublisher", lambda: FakePublisher())
    response = client.post(
        f"/api/v1/publications/{pub.id}/publish?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "public_video_url": "https://assets.example/video.mp4",
            "privacy_level": "SELF_ONLY",
            "is_aigc": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PROCESSING"
    assert body["remote_id"] == "pub-123"
    assert submitted["format"] == "VIDEO"
    assert submitted["video_url"] == "https://assets.example/video.mp4"
    assert submitted["is_aigc"] is True

    db.expire_all()
    refreshed = db.get(Publication, pub.id)
    assert refreshed.status == "PROCESSING"
    assert refreshed.remote_id == "pub-123"
    audit = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == pub.id,
            AuditEvent.action == "PUBLICATION_API_SUBMITTED",
        )
    ).one()
    assert audit.actor_id is not None
    assert audit.profile_id == profile.id


def test_tiktok_status_marks_published_only_after_completion(client, db, monkeypatch):
    ws, profile, pub = _world(db)
    pub.status = "PROCESSING"
    pub.remote_id = "pub-456"
    db.commit()

    class FakePublisher:
        def status(self, publish_id):
            assert publish_id == "pub-456"
            return {
                "publish_id": publish_id,
                "status": "PUBLISH_COMPLETE",
                "post_ids": [987654321],
                "fail_reason": None,
            }

    monkeypatch.setattr(tiktok_module, "TikTokPublisher", lambda: FakePublisher())
    response = client.post(
        f"/api/v1/publications/{pub.id}/status?workspace_id={ws.id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PUBLISHED"
    assert body["platform_status"] == "PUBLISH_COMPLETE"
    assert body["remote_id"] == "987654321"

    db.expire_all()
    refreshed = db.get(Publication, pub.id)
    assert refreshed.status == "PUBLISHED"
    assert refreshed.remote_id == "987654321"


def test_tiktok_local_video_path_is_confined_to_asset_root(client, db):
    ws, profile, pub = _world(db)
    response = client.post(
        f"/api/v1/publications/{pub.id}/publish?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "local_video_path": "C:/Windows/System32/video.mp4",
            "privacy_level": "SELF_ONLY",
        },
    )
    assert response.status_code == 409
    assert "ASSET_ROOT" in response.json()["detail"]


@pytest.fixture()
def client(db):
    def override_session():
        yield db

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
