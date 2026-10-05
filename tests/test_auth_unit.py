"""Database-independent tests for login primitives and workspace authorization."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.auth import (
    get_current_user,
    require_allowed_origin,
    require_workspace_access,
    token_digest,
)
from apps.api.auth_routes import (
    LoginInput,
    RegistrationInput,
    _LoginLimiter,
)
from apps.api.main import app
from packages.shared.db import get_session


def test_registration_normalizes_email_and_requires_long_password():
    request = RegistrationInput(email="  USER@Example.com ", password="long-password-1")
    assert request.email == "user@example.com"

    with pytest.raises(ValueError):
        RegistrationInput(email="user@example.com", password="short")


def test_password_hash_is_one_way_and_verifiable():
    password = "correct horse battery staple"
    hashed = PasswordHasher().hash(password)

    assert hashed != password
    assert PasswordHasher().verify(hashed, password)
    assert token_digest("raw-session-token") != "raw-session-token"


def test_login_input_normalizes_email():
    assert LoginInput(email=" USER@EXAMPLE.COM ", password="x").email == "user@example.com"


def test_login_limiter_blocks_after_threshold_and_clears_on_success():
    limiter = _LoginLimiter()
    for _ in range(5):
        limiter.record_failure("127.0.0.1")

    assert limiter.is_limited("127.0.0.1")
    limiter.clear("127.0.0.1")
    assert not limiter.is_limited("127.0.0.1")


def test_workspace_access_fails_closed_for_non_member():
    user = SimpleNamespace(id=uuid4())

    class NoMembershipSession:
        def scalar(self, statement):
            return None

    with pytest.raises(HTTPException) as error:
        require_workspace_access(
            SimpleNamespace(method="GET"), uuid4(), user, NoMembershipSession()
        )

    assert error.value.status_code == 404


def test_workspace_mutation_rejects_untrusted_origin():
    user = SimpleNamespace(id=uuid4())

    class SessionStub:
        def scalar(self, statement):
            raise AssertionError("origin must be checked before workspace lookup")

    with pytest.raises(HTTPException) as error:
        require_workspace_access(
            SimpleNamespace(method="POST", headers={"origin": "https://attacker.example"}),
            uuid4(),
            user,
            SessionStub(),
        )

    assert error.value.status_code == 403


def test_configured_frontend_origin_is_allowed():
    require_allowed_origin(
        SimpleNamespace(headers={"origin": "http://localhost:5173"})
    )


def test_current_user_requires_and_resolves_a_hashed_session():
    raw_token = "opaque-session-token"
    user = SimpleNamespace(id=uuid4())
    auth_session = SimpleNamespace(user_id=user.id)

    class SessionStub:
        def scalar(self, statement):
            return auth_session

        def get(self, model, user_id):
            assert user_id == user.id
            return user

    assert get_current_user(raw_token, SessionStub()) is user
    assert token_digest(raw_token) != raw_token

    with pytest.raises(HTTPException) as error:
        get_current_user(None, SessionStub())
    assert error.value.status_code == 401


def test_protected_api_rejects_missing_session():
    class EmptySession:
        def scalar(self, statement):
            return None

    def override_session():
        yield EmptySession()

    previous = app.dependency_overrides.copy()
    app.dependency_overrides.pop(require_workspace_access, None)
    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get(f"/api/v1/jobs?workspace_id={uuid4()}")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 401
