"""Email/password session lifecycle integration tests."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from packages.shared.db import get_session


def test_register_verify_login_me_logout_and_revocation(db, monkeypatch):
    from apps.api import auth_routes
    from apps.api.auth import require_workspace_access
    from packages.shared.settings import Settings

    issued_tokens = []
    email = f"new-user-{uuid4().hex}@example.test"
    monkeypatch.setattr(
        auth_routes,
        "get_settings",
        lambda: Settings(
            app_env="test",
            smtp_host="mail.example.test",
            smtp_from_email="noreply@example.test",
        ),
    )
    monkeypatch.setattr(
        auth_routes,
        "_deliver_without_disclosing_account_state",
        lambda user, raw_token, purpose: issued_tokens.append((raw_token, purpose)),
    )

    def override_session():
        yield db

    app.dependency_overrides.pop(require_workspace_access, None)
    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        registered = client.post(
            "/api/v1/auth/register",
            headers={"Origin": "http://localhost:5173"},
            json={
                "email": email,
                "password": "a-strong-test-password",
                "name": "New User",
            },
        )
        assert registered.status_code == 202
        assert "urdia_session" not in registered.cookies
        assert registered.headers["cache-control"] == "no-store"
        assert len(issued_tokens) == 1
        workspace_id = None
        from packages.domain.models import Profile, Workspace
        profile_rows = db.scalars(select(Profile).order_by(Profile.created_at.desc())).all()
        assert profile_rows[0].key == "default"
        assert profile_rows[0].name == "Default Profile"
        assert profile_rows[0].editorial_policy["human_approval_required"] is True
        assert profile_rows[0].editorial_policy.get("legacy_channel_identity") is None
        workspace_id = profile_rows[0].workspace_id
        assert db.get(Workspace, workspace_id) is not None
        duplicate_registration = client.post(
            "/api/v1/auth/register",
            headers={"Origin": "http://localhost:5173"},
            json={
                "email": email.upper(),
                "password": "a-different-test-password",
            },
        )
        assert duplicate_registration.status_code == registered.status_code
        assert duplicate_registration.json() == registered.json()
        verification_token, purpose = issued_tokens.pop()
        assert purpose == auth_routes.VERIFY_EMAIL
        assert client.get("/api/v1/auth/me").status_code == 401
        unverified_login = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": email, "password": "a-strong-test-password"},
        )
        assert unverified_login.status_code == 401

        verified = client.post(
            "/api/v1/auth/verification/confirm",
            headers={"Origin": "http://localhost:5173"},
            json={"token": verification_token},
        )
        assert verified.status_code == 200
        reused_token = client.post(
            "/api/v1/auth/verification/confirm",
            headers={"Origin": "http://localhost:5173"},
            json={"token": verification_token},
        )
        assert reused_token.status_code == 400

        logged_in = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": email.upper(), "password": "a-strong-test-password"},
        )
        assert logged_in.status_code == 200
        assert "urdia_session" in logged_in.cookies
        assert logged_in.headers["cache-control"] == "no-store"

        context = logged_in.json()
        workspace_id = context["workspaces"][0]["id"]
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.get(f"/api/v1/jobs?workspace_id={workspace_id}").status_code == 200
        assert client.get(
            "/api/v1/jobs?workspace_id=00000000-0000-0000-0000-000000000001"
        ).status_code == 404

        reset_requested = client.post(
            "/api/v1/auth/password-reset/request",
            headers={"Origin": "http://localhost:5173"},
            json={"email": email},
        )
        assert reset_requested.status_code == 202
        unknown_reset_requested = client.post(
            "/api/v1/auth/password-reset/request",
            headers={"Origin": "http://localhost:5173"},
            json={"email": "unknown-user@example.test"},
        )
        assert unknown_reset_requested.status_code == reset_requested.status_code
        assert unknown_reset_requested.json() == reset_requested.json()
        reset_token, purpose = issued_tokens.pop()
        assert purpose == auth_routes.RESET_PASSWORD
        reset_confirmed = client.post(
            "/api/v1/auth/password-reset/confirm",
            headers={"Origin": "http://localhost:5173"},
            json={"token": reset_token, "new_password": "another-strong-password"},
        )
        assert reset_confirmed.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401

        old_password_login = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": email, "password": "a-strong-test-password"},
        )
        assert old_password_login.status_code == 401

        login_again = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": email.upper(), "password": "another-strong-password"},
        )
        assert login_again.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 200

        logged_out = client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://localhost:5173"}
        )
        assert logged_out.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_registration_is_disabled_outside_local_environments(db, monkeypatch):
    from apps.api import auth_routes
    from packages.domain.models import User
    from packages.shared.settings import Settings

    monkeypatch.setattr(
        auth_routes,
        "get_settings",
        lambda: Settings(
            app_env="production",
            smtp_host="mail.example.test",
            smtp_from_email="noreply@example.test",
        ),
    )

    def override_session():
        yield db

    email = f"blocked-{uuid4().hex}@example.test"
    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).post(
            "/api/v1/auth/register",
            headers={"Origin": "http://localhost:5173"},
            json={
                "email": email,
                "password": "a-strong-test-password",
            },
        )

        assert response.status_code == 503
        assert db.query(User).filter_by(email=email).first() is None
    finally:
        app.dependency_overrides.clear()
