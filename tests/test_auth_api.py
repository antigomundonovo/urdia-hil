"""Email/password session lifecycle integration tests."""

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.shared.db import get_session


def test_register_login_me_logout_and_revocation(db):
    def override_session():
        yield db

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        registered = client.post(
            "/api/v1/auth/register",
            headers={"Origin": "http://localhost:5173"},
            json={
                "email": "new-user@example.test",
                "password": "a-strong-test-password",
                "name": "New User",
            },
        )
        assert registered.status_code == 201
        assert "urdia_session" in registered.cookies
        assert registered.headers["cache-control"] == "no-store"
        assert "httponly" in registered.headers["set-cookie"].lower()
        context = registered.json()
        assert context["user"]["email"] == "new-user@example.test"
        assert len(context["workspaces"]) == 1
        workspace_id = context["workspaces"][0]["id"]

        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.get(f"/api/v1/jobs?workspace_id={workspace_id}").status_code == 200

        logged_out = client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://localhost:5173"}
        )
        assert logged_out.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

        logged_in = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": "NEW-USER@example.test", "password": "a-strong-test-password"},
        )
        assert logged_in.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 200
    finally:
        app.dependency_overrides.clear()
