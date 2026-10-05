"""Auxiliary memory service + API (Doc 05 §Memory; V2.2 Hermes)."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.auth_routes import PASSWORD_HASHER
from apps.api.main import app
from packages.domain.models import User, Workspace, WorkspaceMember
from packages.research.memory import MemoryError, MemoryService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

ORIGIN = {"Origin": "http://localhost:5173"}


def _override_session(db):
    def override():
        yield db

    app.dependency_overrides[get_session] = override


def _seed_member(db):
    user = User(
        name="Memory User",
        email=f"memory-{uuid4().hex[:8]}@example.test",
        password_hash=PASSWORD_HASHER.hash("a-strong-test-password"),
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    workspace = Workspace(name="Memory WS")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id))
    db.commit()
    return user, workspace


def _login(client, user):
    resp = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": user.email, "password": "a-strong-test-password"},
    )
    assert resp.status_code == 200, resp.text
    return {"Cookie": resp.headers["set-cookie"].split(";")[0], **ORIGIN}


def test_fact_without_origin_fails_closed(db):
    workspace = Workspace(name="Memory Unit WS")
    db.add(workspace)
    db.commit()
    ctx = ExecutionContext(workspace_id=workspace.id)
    svc = MemoryService(db)
    try:
        svc.remember(ctx, kind="FACT", content="bondinho é de 1912")
        raise AssertionError("should have raised")
    except MemoryError as exc:
        assert "FACT requires origin" in str(exc)
    # With origin it passes.
    entry = svc.remember(
        ctx,
        kind="FACT",
        content="bondinho é de 1912",
        origin={"source_type": "dataset", "source_id": "historical_facts.json"},
    )
    assert entry.kind == "FACT"
    # Unknown kind fails.
    try:
        svc.remember(ctx, kind="RUMOR", content="x")
        raise AssertionError("should have raised")
    except MemoryError as exc:
        assert "unknown memory kind" in str(exc)


def test_memory_api_lifecycle(db):
    _override_session(db)
    user, workspace = _seed_member(db)
    try:
        client = TestClient(app)
        headers = _login(client, user)

        created = client.post(
            "/api/v1/memory",
            headers=headers,
            json={
                "workspace_id": str(workspace.id),
                "kind": "PREFERENCE",
                "content": "Público prefere histórias com data precisa",
                "confidence": 0.7,
            },
        )
        assert created.status_code == 201, created.text
        memory_id = created.json()["id"]

        listed = client.get(
            "/api/v1/memory",
            headers=headers,
            params={"workspace_id": str(workspace.id)},
        )
        assert listed.status_code == 200
        assert [m["id"] for m in listed.json()] == [memory_id]

        # FACT through the API also fails closed.
        factless = client.post(
            "/api/v1/memory",
            headers=headers,
            json={
                "workspace_id": str(workspace.id),
                "kind": "FACT",
                "content": "sem origem",
            },
        )
        assert factless.status_code == 422

        # Supersede: new active entry, old one SUPERSEDED with pointer.
        superseded = client.post(
            f"/api/v1/memory/{memory_id}/supersede",
            headers=headers,
            json={
                "workspace_id": str(workspace.id),
                "kind": "PREFERENCE",
                "content": "Público prefere datas e fontes primárias",
                "confidence": 0.8,
            },
        )
        assert superseded.status_code == 201, superseded.text
        new_id = superseded.json()["id"]
        assert new_id != memory_id

        listed = client.get(
            "/api/v1/memory",
            headers=headers,
            params={"workspace_id": str(workspace.id)},
        )
        assert [m["id"] for m in listed.json()] == [new_id]

        # Archive removes from active list.
        archived = client.post(
            f"/api/v1/memory/{new_id}/archive",
            headers=headers,
            params={"workspace_id": str(workspace.id)},
        )
        assert archived.status_code == 200
        listed = client.get(
            "/api/v1/memory",
            headers=headers,
            params={"workspace_id": str(workspace.id)},
        )
        assert listed.json() == []

        # Non-member workspace is invisible (404).
        other_ws = str(uuid4())
        intruder = client.get(
            "/api/v1/memory", headers=headers, params={"workspace_id": other_ws}
        )
        assert intruder.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
