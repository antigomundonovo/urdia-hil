"""Instagram publisher tests — all HTTP mocked; NOTHING is really posted."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from packages.domain.editorial import ContentPackage, Draft
from packages.domain.models import AuditEvent, Profile, User, Workspace, WorkspaceMember
from apps.api.auth import get_current_user
from packages.domain.publishing import Publication
from packages.providers import instagram as ig_module
from packages.providers.instagram import (
    InstagramPublisher,
    InstagramPublishError,
)
from packages.shared.db import get_session


def _response(status_code: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=body or {},
        headers={"content-type": "application/json"},
    )


# --- validate_payload --------------------------------------------------------


def test_validate_rejects_local_image_paths():
    publisher = InstagramPublisher(token="t")
    with pytest.raises(InstagramPublishError, match="not public"):
        publisher.validate_payload(
            {
                "format": "PHOTO_POST",
                "caption": "legenda",
                "image_urls": ["C:/urdia-hil/assets/originals/x.png"],
            }
        )


def test_validate_rejects_oversized_caption():
    publisher = InstagramPublisher(token="t")
    with pytest.raises(InstagramPublishError, match="caption exceeds"):
        publisher.validate_payload(
            {
                "format": "PHOTO_POST",
                "caption": "x" * 2201,
                "image_urls": ["https://host.test/a.png"],
            }
        )


def test_validate_rejects_empty_images_and_bad_counts():
    publisher = InstagramPublisher(token="t")
    with pytest.raises(InstagramPublishError, match="no image_urls"):
        publisher.validate_payload(
            {"format": "PHOTO_POST", "caption": "x", "image_urls": []}
        )
    with pytest.raises(InstagramPublishError, match="exactly 1"):
        publisher.validate_payload(
            {
                "format": "PHOTO_POST",
                "caption": "x",
                "image_urls": ["https://a/1.png", "https://a/2.png"],
            }
        )
    with pytest.raises(InstagramPublishError, match="CAROUSEL requires"):
        publisher.validate_payload(
            {"format": "CAROUSEL", "caption": "x", "image_urls": ["https://a/1.png"]}
        )


# --- publish flows (mocked _post) ---------------------------------------------


def test_publish_photo_flow(monkeypatch):
    publisher = InstagramPublisher(token="t")
    calls: list[tuple[str, dict]] = []

    def fake_post(path, data):
        calls.append((path, dict(data)))
        if path == "media":
            return {"id": "container-1"}
        return {"id": "ig-media-999"}

    monkeypatch.setattr(publisher, "_post", fake_post)
    monkeypatch.setattr(publisher, "_permalink", lambda rid: "https://instagram.com/p/xyz")
    result = publisher.publish(
        {
            "format": "PHOTO_POST",
            "caption": "Um marco de 1912",
            "image_urls": ["https://host.test/photo.png"],
        },
        idempotency_key="k1",
    )
    assert result.remote_id == "ig-media-999"
    assert result.permalink == "https://instagram.com/p/xyz"
    # 2-step flow: container then publish
    assert [p for p, _ in calls] == ["media", "media_publish"]
    assert calls[1][1]["creation_id"] == "container-1"


def test_post_attaches_token_to_http_body(monkeypatch):
    """The token travels in every HTTP body (added by _post, above the
    monkeypatch line of the flow tests)."""
    sent: list[dict] = []

    def fake_post(url, data=None, timeout=None):
        sent.append(dict(data or {}))
        return _response(200, {"id": "x"})

    monkeypatch.setattr(ig_module.httpx, "post", fake_post)
    publisher = InstagramPublisher(token="TOKEN-DE-TESTE")
    out = publisher._post("media", {"image_url": "https://h/a.png"})
    assert out == {"id": "x"}
    assert sent[0]["access_token"] == "TOKEN-DE-TESTE"


def test_publish_carousel_flow(monkeypatch):
    publisher = InstagramPublisher(token="t")
    created: list[str] = []

    def fake_post(path, data):
        if path == "media":
            if data.get("media_type") == "CAROUSEL":
                return {"id": "carousel-container"}
            created.append(data["image_url"])
            return {"id": f"child-{len(created)}"}
        return {"id": "carousel-777"}

    monkeypatch.setattr(publisher, "_post", fake_post)
    result = publisher.publish(
        {
            "format": "CAROUSEL",
            "caption": "Dois momentos",
            "image_urls": ["https://h/1.png", "https://h/2.png"],
        },
        idempotency_key="k2",
    )
    assert result.remote_id == "carousel-777"
    assert len(created) == 2  # one container per child


def test_publish_api_error_is_normalized(monkeypatch):
    publisher = InstagramPublisher(token="t")
    monkeypatch.setattr(
        ig_module.httpx,
        "post",
        lambda *a, **kw: _response(
            400, {"error": {"message": "The image URL is not reachable"}}
        ),
    )
    with pytest.raises(InstagramPublishError, match="not reachable"):
        publisher.publish(
            {
                "format": "PHOTO_POST",
                "caption": "x",
                "image_urls": ["https://host.test/a.png"],
            },
            idempotency_key="k",
        )


def test_error_messages_never_contain_token():
    publisher = InstagramPublisher(token="SEGREDO-ULTRA")
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            ig_module.httpx,
            "post",
            lambda *a, **kw: _response(500, {"error": {"message": "boom"}}),
        )
        with pytest.raises(InstagramPublishError) as exc_info:
            publisher.publish(
                {
                    "format": "PHOTO_POST",
                    "caption": "x",
                    "image_urls": ["https://h/a.png"],
                },
                idempotency_key="k",
            )
    finally:
        monkeypatch.undo()
    assert "SEGREDO-ULTRA" not in str(exc_info.value)


# --- token lifecycle ----------------------------------------------------------


def test_refresh_long_lived(monkeypatch):
    publisher = InstagramPublisher(token="old")
    monkeypatch.setattr(
        ig_module.httpx,
        "get",
        lambda *a, **kw: _response(
            200, {"access_token": "new", "expires_in": 5184000}
        ),
    )
    result = publisher.refresh_long_lived()
    assert result["access_token"] == "new"
    assert result["expires_in"] == 60 * 86400


def test_revoke_best_effort_never_raises(monkeypatch):
    publisher = InstagramPublisher(token="t")

    def boom(*a, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(ig_module.httpx, "delete", boom)
    assert publisher.revoke_account("17841427289016710") is False


# --- API route: publish on a PENDING publication ------------------------------


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def pending_publication(db):
    """Workspace + profile + package + draft + PENDING instagram publication."""
    ws = Workspace(name=f"igpub-{uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    from packages.domain.editorial import CanonicalContent, Opportunity

    opp = Opportunity(
        workspace_id=ws.id,
        profile_id=profile.id,
        title="Publicação IG",
    )
    db.add(opp)
    db.flush()
    canonical = CanonicalContent(
        workspace_id=ws.id,
        opportunity_id=opp.id,
        key_message="bondinho 1912",
    )
    db.add(canonical)
    db.flush()
    package = ContentPackage(
        workspace_id=ws.id,
        opportunity_id=opp.id,
        canonical_content_id=canonical.id,
        format="PHOTO_POST",
    )
    db.add(package)
    db.flush()
    db.add(
        Draft(
            workspace_id=ws.id,
            content_package_id=package.id,
            title="Bondinho 1912",
            caption="O primeiro trecho começou a operar em 1912.",
        )
    )
    pub = Publication(
        workspace_id=ws.id,
        profile_id=profile.id,
        content_package_id=package.id,
        platform="instagram",
        method="EXPORT",
        status="PENDING",
        idempotency_key=f"{profile.id}:{package.id}:instagram:v1",
    )
    db.add(pub)
    db.commit()
    actor = User(
        name="Instagram Publisher",
        email=f"instagram-publisher-{uuid4().hex[:8]}@example.test",
    )
    db.add(actor)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=actor.id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: actor
    db.expire_all()
    return ws, profile, pub


def test_api_publish_route_publishes(client, db, pending_publication, monkeypatch):
    ws, profile, pub = pending_publication
    published: dict = {}

    class FakePublisher:
        def publish(self, payload, *, idempotency_key):
            published.update(payload)
            published["idempotency_key"] = idempotency_key
            return SimpleNamespace(remote_id="ig-123", permalink="https://ig/p/1")

    monkeypatch.setattr(ig_module, "InstagramPublisher", lambda: FakePublisher())
    resp = client.post(
        f"/api/v1/publications/{pub.id}/publish?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "public_image_urls": ["https://host.test/photo.png"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "PUBLISHED"
    assert body["method"] == "API"
    assert body["remote_id"] == "ig-123"
    # caption composed from the draft (title + blank line + caption)
    assert published["caption"].startswith("Bondinho 1912")
    assert published["image_urls"] == ["https://host.test/photo.png"]
    assert published["idempotency_key"]

    db.expire_all()
    refreshed = db.get(Publication, pub.id)
    assert refreshed.status == "PUBLISHED"
    assert refreshed.method == "API"
    assert refreshed.remote_id == "ig-123"
    audit = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == pub.id,
            AuditEvent.action == "PUBLICATION_API_PUBLISHED",
        )
    ).one()
    assert audit.actor_id is not None
    assert audit.profile_id == profile.id


def test_api_publish_route_rejects_non_pending(client, db, pending_publication):
    ws, profile, pub = pending_publication
    pub.status = "PUBLISHED"
    db.commit()
    resp = client.post(
        f"/api/v1/publications/{pub.id}/publish?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "public_image_urls": ["https://host.test/photo.png"],
        },
    )
    assert resp.status_code == 409
    assert "PENDING" in resp.json()["detail"]


def test_api_publish_route_rejects_local_images(client, db, pending_publication):
    ws, profile, pub = pending_publication
    resp = client.post(
        f"/api/v1/publications/{pub.id}/publish?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "public_image_urls": ["C:/local/file.png"],
        },
    )
    assert resp.status_code == 409
    assert "not public" in resp.json()["detail"]
