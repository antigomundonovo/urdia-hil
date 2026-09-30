"""Email/password sign-in with revocable opaque sessions."""

import re
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.auth import (
    SESSION_COOKIE,
    get_current_user,
    require_allowed_origin,
    token_digest,
)
from packages.domain.models import AuthSession, Profile, User, Workspace, WorkspaceMember
from packages.domain.profile_defaults import ANM_EDITORIAL_POLICY, ANM_PROFILE_KEY
from packages.shared.db import get_session
from packages.shared.settings import get_settings

router = APIRouter(prefix="/api/v1/auth")
PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
SESSION_LIFETIME = timedelta(hours=12)
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60


class _LoginLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def is_limited(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            failures = [
                t
                for t in self._failures.get(key, [])
                if now - t < LOGIN_FAILURE_WINDOW_SECONDS
            ]
            if failures:
                self._failures[key] = failures
            else:
                self._failures.pop(key, None)
            return len(failures) >= LOGIN_FAILURE_LIMIT

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._failures) > 10_000:
                self._failures = {
                    entry: [t for t in times if now - t < LOGIN_FAILURE_WINDOW_SECONDS]
                    for entry, times in self._failures.items()
                    if any(now - t < LOGIN_FAILURE_WINDOW_SECONDS for t in times)
                }
            failures = [
                t for t in self._failures.get(key, []) if now - t < LOGIN_FAILURE_WINDOW_SECONDS
            ]
            failures.append(now)
            self._failures[key] = failures

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = _LoginLimiter()


class RegistrationInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("invalid email address")
        return email


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


def _set_session_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.app_env.lower() not in {"development", "test"},
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _new_session(session: Session, user: User, response: Response) -> None:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_digest(raw_token),
            expires_at=datetime.now(UTC) + SESSION_LIFETIME,
        )
    )
    session.flush()
    _set_session_cookie(response, raw_token)


def _auth_payload(session: Session, user: User) -> dict:
    memberships = session.scalars(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    ).all()
    workspaces = []
    for membership in memberships:
        workspace = session.get(Workspace, membership.workspace_id)
        if workspace is None:
            continue
        profile = session.scalar(
            select(Profile)
            .where(Profile.workspace_id == workspace.id)
            .order_by(Profile.key)
            .limit(1)
        )
        workspaces.append(
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "profile": (
                    {
                        "id": str(profile.id),
                        "key": profile.key,
                        "name": profile.name,
                        "language": profile.language,
                        "status": profile.status,
                    }
                    if profile
                    else None
                ),
            }
        )
    workspaces.sort(key=lambda item: item["name"])
    return {
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "workspaces": workspaces,
    }


@router.post("/register", status_code=201)
def register(
    body: RegistrationInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    user = User(
        email=body.email,
        name=body.name.strip() if body.name and body.name.strip() else body.email.split("@")[0],
        password_hash=PASSWORD_HASHER.hash(body.password),
    )
    workspace = Workspace(name=f"Workspace {uuid4().hex[:12]}")
    session.add_all([user, workspace])
    try:
        session.flush()
        profile = Profile(
            workspace_id=workspace.id,
            key=ANM_PROFILE_KEY,
            name="Antigo Mundo Novo",
            language=ANM_EDITORIAL_POLICY["language"],
            audience_region=ANM_EDITORIAL_POLICY["audience"],
            editorial_policy=ANM_EDITORIAL_POLICY,
            automation_level=ANM_EDITORIAL_POLICY["automation_level"],
            status="ACTIVE",
        )
        session.add_all(
            [
                profile,
                WorkspaceMember(workspace_id=workspace.id, user_id=user.id),
            ]
        )
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="account could not be created") from exc
    _new_session(session, user, response)
    session.commit()
    return _auth_payload(session, user)


@router.post("/login")
def login(
    body: LoginInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    client_host = request.client.host if request.client else "unknown"
    limiter_key = client_host
    if login_limiter.is_limited(limiter_key):
        raise HTTPException(status_code=429, detail="too many login attempts")

    user = session.scalar(select(User).where(User.email == body.email))
    password_hash = (
        user.password_hash
        if user is not None and user.password_hash
        else DUMMY_PASSWORD_HASH
    )
    try:
        valid = PASSWORD_HASHER.verify(password_hash, body.password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        valid = False
    if not valid or user is None:
        login_limiter.record_failure(limiter_key)
        raise HTTPException(status_code=401, detail="invalid email or password")

    if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = PASSWORD_HASHER.hash(body.password)
    login_limiter.clear(limiter_key)
    _new_session(session, user, response)
    session.commit()
    return _auth_payload(session, user)


@router.get("/me")
def current_session(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    response.headers["Cache-Control"] = "no-store"
    payload = _auth_payload(session, user)
    if not payload["workspaces"]:
        raise HTTPException(status_code=403, detail="no workspace membership")
    return payload


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    if session_token:
        auth_session = session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == token_digest(session_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        if auth_session is not None:
            auth_session.revoked_at = datetime.now(UTC)
            session.commit()
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=get_settings().app_env.lower() not in {"development", "test"},
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
