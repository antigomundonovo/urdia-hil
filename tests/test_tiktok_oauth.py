"""TikTok OAuth routes tests — exchange HTTP is mocked; token saved to a
temporary .env (never the real one, never logged)."""

import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api import tiktok_routes as tt
from apps.api.auth import get_current_user
from apps.api.main import app
from packages.domain.models import User


@pytest.fixture()
def authed(db):
    actor = User(
        name="Owner",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.test",
    )
    db.add(actor)
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: actor
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("POSTGRES_PASSWORD=x\n", encoding="utf-8")
    return tmp_path


def test_authorize_blocks_without_client_key(authed, tmp_env, monkeypatch):
    import types

    monkeypatch.setattr(
        tt,
        "_settings",
        lambda: types.SimpleNamespace(tiktok_client_key=""),
    )
    resp = authed.get("/api/v1/social/tiktok/authorize")
    assert resp.status_code == 409
    assert "TIKTOK_CLIENT_KEY" in resp.json()["detail"]


def test_authorize_returns_consent_url(authed, tmp_env):
    import types

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            tt,
            "_settings",
            lambda: types.SimpleNamespace(tiktok_client_key="KEY123"),
        )
        resp = authed.get("/api/v1/social/tiktok/authorize")
    finally:
        monkeypatch.undo()
    assert resp.status_code == 200
    url = resp.json()["authorize_url"]
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert "client_key=KEY123" in url
    assert "video.publish" in url
    assert "antigomundonovo.github.io" in url
    assert resp.json()["state"]


def test_exchange_persists_token_locally(authed, tmp_env, monkeypatch):
    import types

    monkeypatch.setattr(
        tt,
        "_settings",
        lambda: types.SimpleNamespace(
            tiktok_client_key="KEY123", tiktok_client_secret="SECRET123"
        ),
    )
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured.update(data or {})
        return httpx.Response(
            200,
            json={
                "access_token": "tiktok-long-token",
                "open_id": "open-1",
                "scope": "video.publish",
                "expires_in": 86400,
            },
        )

    monkeypatch.setattr(tt.httpx, "post", fake_post)
    resp = authed.post(
        "/api/v1/social/tiktok/exchange", json={"code": "abc123"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"
    assert resp.json()["open_id"] == "open-1"
    # token stored in the LOCAL .env, secret never sent to the response
    env_text = (tmp_env / ".env").read_text(encoding="utf-8")
    assert "TIKTOK_ACCESS_TOKEN=tiktok-long-token" in env_text
    assert "TIKTOK_OPEN_ID=open-1" in env_text
    assert "tiktok-long-token" not in resp.text
    assert captured["code"] == "abc123"
    assert captured["client_key"] == "KEY123"
    assert captured["grant_type"] == "authorization_code"


def test_exchange_fails_closed_without_credentials(authed, tmp_env):
    import types

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            tt,
            "_settings",
            lambda: types.SimpleNamespace(tiktok_client_key="", tiktok_client_secret=""),
        )
        resp = authed.post("/api/v1/social/tiktok/exchange", json={"code": "x"})
    finally:
        monkeypatch.undo()
    assert resp.status_code == 409


def test_exchange_reports_tiktok_errors(authed, tmp_env, monkeypatch):
    import types

    monkeypatch.setattr(
        tt,
        "_settings",
        lambda: types.SimpleNamespace(
            tiktok_client_key="K", tiktok_client_secret="S"
        ),
    )
    monkeypatch.setattr(
        tt.httpx,
        "post",
        lambda *a, **kw: httpx.Response(
            400, json={"error": "invalid_code", "error_description": "code expired"}
        ),
    )
    resp = authed.post("/api/v1/social/tiktok/exchange", json={"code": "x"})
    assert resp.status_code == 409
    assert "code expired" in resp.json()["detail"]


def test_connection_status(authed, tmp_env, monkeypatch):
    import types

    monkeypatch.setattr(
        tt,
        "_settings",
        lambda: types.SimpleNamespace(
            tiktok_access_token="", tiktok_open_id=None
        ),
    )
    resp = authed.get("/api/v1/social/tiktok/connection")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False
