"""Studio⇄HIL bridge: machine clients and demand export (Emenda 002)."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.auth import token_digest
from apps.api.bridge_routes import MACHINE_KEY_PREFIX
from apps.api.main import app
from packages.domain.models import MachineClient, User, Workspace, WorkspaceMember
from packages.domain.social import AudienceDemand
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

ORIGIN = {"Origin": "http://localhost:5173"}


def _seed_owner(db):
    user = User(
        name="Bridge Owner",
        email=f"bridge-{db.query(User).count()}-{id(db) % 99999}@example.test",
        password_hash="x",
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    workspace = Workspace(name="Bridge WS")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id))
    db.commit()
    return user, workspace


def _login_cookie(client, email):
    # Direct session insert path is not exposed; use the login route with a
    # real password set via the API's own hasher.
    return client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": email, "password": "a-strong-test-password"},
    )


def _override_session(db):
    def override():
        yield db

    app.dependency_overrides[get_session] = override


def test_machine_client_lifecycle_and_demand_export(db):
    _override_session(db)
    user, workspace = _seed_owner(db)
    # Give the owner a real password hash to log in with.
    from apps.api.auth_routes import PASSWORD_HASHER

    user.password_hash = PASSWORD_HASHER.hash("a-strong-test-password")
    db.commit()

    try:
        client = TestClient(app)
        login = _login_cookie(client, user.email)
        assert login.status_code == 200, login.text

        created = client.post(
            "/api/v1/bridge/clients",
            headers={**ORIGIN, "Cookie": login.headers["set-cookie"].split(";")[0]},
            json={"workspace_id": str(workspace.id), "name": "URDIA Studio"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["api_key"].startswith(MACHINE_KEY_PREFIX)
        api_key = body["api_key"]

        # Key persisted only as digest.
        row = db.scalar(
            select(MachineClient).where(MachineClient.id == body["id"])
        )
        assert row is not None
        assert row.key_hash != api_key
        assert row.revoked_at is None

        # Machine export returns the structured §10 demand.
        db.add(
            AudienceDemand(
                workspace_id=workspace.id,
                summary="Demanda recorrente por história do bondinho de 1912",
                unique_people_count=7,
                growth=0.12,
                engagement=0.34,
                platforms=["instagram"],
                confidence=0.8,
                editorial_fit=0.9,
            )
        )
        db.commit()

        export = client.get(
            "/api/v1/bridge/demand",
            params={"workspace_id": str(workspace.id)},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert export.status_code == 200, export.text
        payload = export.json()
        assert len(payload) == 1
        item = payload[0]
        for field in (
            "summary",
            "evidence",
            "unique_people_count",
            "growth",
            "engagement",
            "platforms",
            "confidence",
            "editorial_fit",
        ):
            assert field in item

        # Machine key cannot reach session-only routers (allowlist holds):
        # a session-authenticated route rejects the machine key outright.
        stray = TestClient(app).get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert stray.status_code == 401

        # No key / wrong key → 401.
        assert (
            client.get(
                "/api/v1/bridge/demand", params={"workspace_id": str(workspace.id)}
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/v1/bridge/demand",
                params={"workspace_id": str(workspace.id)},
                headers={"Authorization": "Bearer urdia_mk_" + "0" * 48},
            ).status_code
            == 401
        )

        # Revoke → key dies.
        revoked = client.delete(
            f"/api/v1/bridge/clients/{body['id']}",
            headers={**ORIGIN, "Cookie": login.headers["set-cookie"].split(";")[0]},
            params={"workspace_id": str(workspace.id)},
        )
        assert revoked.status_code == 204
        assert (
            client.get(
                "/api/v1/bridge/demand",
                params={"workspace_id": str(workspace.id)},
                headers={"Authorization": f"Bearer {api_key}"},
            ).status_code
            == 401
        )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_machine_key_cannot_cross_workspaces(db):
    _override_session(db)
    _, workspace_a = _seed_owner(db)
    _, workspace_b = _seed_owner(db)

    key_raw = MACHINE_KEY_PREFIX + uuid4().hex
    client = MachineClient(
        workspace_id=workspace_a.id,
        name="Key A",
        key_hash=token_digest(key_raw),
    )
    db.add(client)
    db.commit()

    try:
        api = TestClient(app)
        cross = api.get(
            "/api/v1/bridge/demand",
            params={"workspace_id": str(workspace_b.id)},
            headers={"Authorization": f"Bearer {key_raw}"},
        )
        # 404, never data or even existence hints from another workspace.
        assert cross.status_code in (401, 404)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_demand_decision_flows_to_bridge(db):
    from packages.domain.social import AudienceDemand
    from packages.research.social import SocialError, SocialIntelligenceService

    _override_session(db)
    from packages.domain.models import Profile

    workspace = Workspace(name="Decision WS")
    db.add(workspace)
    db.flush()
    profile = Profile(workspace_id=workspace.id, key="default", name="Default")
    db.add(profile)
    db.flush()
    demand = AudienceDemand(
        workspace_id=workspace.id,
        profile_id=profile.id,
        summary="historia do bondinho",
        unique_people_count=2,
        platforms=["instagram"],
    )
    db.add(demand)
    db.commit()
    ctx = ExecutionContext(workspace_id=workspace.id, profile_id=profile.id)

    svc = SocialIntelligenceService(db)
    try:
        svc.decide_demand(ctx, demand.id, decision="MAYBE")
        raise AssertionError("should have raised")
    except SocialError as exc:
        assert "APPROVED or REJECTED" in str(exc)

    decided = svc.decide_demand(
        ctx, demand.id, decision="APPROVED", reason="dono aprovou"
    )
    assert decided.decision == "APPROVED"
    assert decided.decided_at is not None

    # Bridge export carries the decision read-only.
    key_raw = MACHINE_KEY_PREFIX + uuid4().hex
    client = MachineClient(
        workspace_id=workspace.id, name="K", key_hash=token_digest(key_raw)
    )
    db.add(client)
    db.commit()
    try:
        api = TestClient(app)
        payload = api.get(
            "/api/v1/bridge/demand",
            params={"workspace_id": str(workspace.id)},
            headers={"Authorization": f"Bearer {key_raw}"},
        ).json()
        assert payload[0]["decision"] == "APPROVED"
        assert payload[0]["decided_at"]
    finally:
        app.dependency_overrides.pop(get_session, None)
