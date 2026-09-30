"""Registry + audit endpoints (Doc 02): workspace-scoped, 404 on unknown
workspace, empty-safe lists."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.models import Workspace
from packages.shared.db import get_session


@pytest.fixture()
def client(db):
    """Share the test session with the API so fixture data is visible."""
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_workspace(db) -> uuid.UUID:
    ws = Workspace(name=f"api-reg-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    return ws.id


def test_providers_endpoint_scoped_and_404(client, db):
    ws_id = _make_workspace(db)
    resp = client.get(f"/api/v1/providers?workspace_id={ws_id}")
    assert resp.status_code == 200
    assert "providers" in resp.json()

    ghost = uuid.uuid4()
    assert client.get(f"/api/v1/providers?workspace_id={ghost}").status_code == 404


def test_capabilities_endpoint_scoped(client, db):
    ws_id = _make_workspace(db)
    resp = client.get(f"/api/v1/capabilities?workspace_id={ws_id}")
    assert resp.status_code == 200
    assert "capabilities" in resp.json()


def test_audit_endpoint_lists_and_requires_workspace(client, db):
    ws_id = _make_workspace(db)
    resp = client.get(f"/api/v1/audit?workspace_id={ws_id}")
    assert resp.status_code == 200
    assert resp.json()["audit"] == []  # fresh workspace: no events yet
    assert client.get("/api/v1/audit").status_code == 422  # workspace_id required
