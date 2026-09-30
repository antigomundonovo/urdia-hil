"""Email/password sign-in with revocable opaque sessions."""

import logging
import re
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response
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
from packages.domain.models import (
    AuthActionToken,
    AuthSession,
    Profile,
    User,
    Workspace,
    WorkspaceMember,
)
from packages.domain.profile_defaults import ANM_EDITORIAL_POLICY, ANM_PROFILE_KEY
from packages.shared.db import get_session
from packages.shared.email import EmailDeliveryError, send_email
from packages.shared.settings import get_settings

router = APIRouter(prefix="/api/v1/auth")
logger = logging.getLogger(__name__)
PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
SESSION_LIFETIME = timedelta(hours=12)
VERIFY_TOKEN_LIFETIME = timedelta(hours=24)
RESET_TOKEN_LIFETIME = timedelta(minutes=30)
VERIFY_EMAIL = "VERIFY_EMAIL"
RESET_PASSWORD = "RESET_PASSWORD"
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


class EmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenInput(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordResetInput(TokenInput):
    new_password: str = Field(min_length=12, max_length=1024)


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


def _issue_action_token(
    session: Session, user: User, purpose: str, lifetime: timedelta
) -> tuple[AuthActionToken, str]:
    now = datetime.now(UTC)
    old_tokens = session.scalars(
        select(AuthActionToken)
        .where(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == purpose,
            AuthActionToken.used_at.is_(None),
        )
        .with_for_update()
    )
    for old_token in old_tokens:
        old_token.used_at = now
    raw_token = secrets.token_urlsafe(32)
    record = AuthActionToken(
        user_id=user.id,
        token_hash=token_digest(raw_token),
        purpose=purpose,
        expires_at=now + lifetime,
    )
    session.add(record)
    session.flush()
    return record, raw_token


def _send_action_email(recipient: str, raw_token: str, *, purpose: str) -> None:
    settings = get_settings()
    action = "verify" if purpose == VERIFY_EMAIL else "reset"
    link = f"{settings.frontend_base_url.rstrip('/')}#{urlencode({action: raw_token})}"
    if purpose == VERIFY_EMAIL:
        subject = "Confirme seu e-mail na URDIA"
        body = (
            "Para confirmar seu e-mail, abra o link abaixo. Ele expira em 24 horas "
            "e pode ser usado uma única vez.\n\n"
            f"{link}\n\nSe você não criou uma conta URDIA, ignore esta mensagem."
        )
    else:
        subject = "Redefina sua senha da URDIA"
        body = (
            "Para escolher uma nova senha, abra o link abaixo. Ele expira em 30 minutos "
            "e pode ser usado uma única vez.\n\n"
            f"{link}\n\nSe você não solicitou a redefinição, ignore esta mensagem."
        )
    send_email(settings, recipient=recipient, subject=subject, body=body)


def _deliver_without_disclosing_account_state(
    recipient: str, raw_token: str, purpose: str
) -> None:
    try:
        _send_action_email(recipient, raw_token, purpose=purpose)
    except EmailDeliveryError:
        # Never log recipient addresses, action tokens, SMTP responses or credentials.
        logger.error("account email delivery failed (purpose=%s)", purpose)


def _rate_limit_request(request: Request, purpose: str) -> None:
    host = request.client.host if request.client else "unknown"
    key = f"{purpose}:{host}"
    if login_limiter.is_limited(key):
        raise HTTPException(status_code=429, detail="too many account requests")
    login_limiter.record_failure(key)


def _valid_action_token(
    session: Session, raw_token: str, purpose: str
) -> AuthActionToken | None:
    return session.scalar(
        select(AuthActionToken)
        .where(
            AuthActionToken.token_hash == token_digest(raw_token),
            AuthActionToken.purpose == purpose,
            AuthActionToken.used_at.is_(None),
            AuthActionToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )


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


@router.post("/register", status_code=202)
def register(
    body: RegistrationInput,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    _rate_limit_request(request, "REGISTER_ACCOUNT")
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise HTTPException(status_code=503, detail="email verification is not configured")
    response.headers["Cache-Control"] = "no-store"
    user = User(
        email=body.email,
        name=body.name.strip() if body.name and body.name.strip() else body.email.split("@")[0],
        password_hash=PASSWORD_HASHER.hash(body.password),
    )
    workspace = Workspace(name=f"Workspace {uuid4().hex[:12]}")
    session.add_all([user, workspace])
    try:
        session.flush()
        _, raw_token = _issue_action_token(
            session, user, VERIFY_EMAIL, VERIFY_TOKEN_LIFETIME
        )
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
    except IntegrityError:
        session.rollback()
        # Do not disclose whether an email address is already registered.
        return {"message": "If the account can be created, verification instructions will be sent."}
    session.commit()
    background_tasks.add_task(
        _deliver_without_disclosing_account_state, body.email, raw_token, VERIFY_EMAIL
    )
    return {"message": "If the account can be created, verification instructions will be sent."}


@router.post("/verification/request", status_code=202)
def request_email_verification(
    body: EmailInput,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    _rate_limit_request(request, VERIFY_EMAIL)
    user = session.scalar(select(User).where(User.email == body.email))
    if user is not None and user.email_verified_at is None:
        _, raw_token = _issue_action_token(
            session, user, VERIFY_EMAIL, VERIFY_TOKEN_LIFETIME
        )
        session.commit()
        background_tasks.add_task(
            _deliver_without_disclosing_account_state, body.email, raw_token, VERIFY_EMAIL
        )
    return {"message": "If the account requires verification, instructions will be sent."}


@router.post("/verification/confirm")
def confirm_email(
    body: TokenInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    response.headers["Cache-Control"] = "no-store"
    token = _valid_action_token(session, body.token, VERIFY_EMAIL)
    if token is None:
        raise HTTPException(status_code=400, detail="verification token is invalid or expired")
    user = session.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="verification token is invalid or expired")
    now = datetime.now(UTC)
    token.used_at = now
    user.email_verified_at = now
    session.commit()
    return {"message": "E-mail confirmado. Entre com sua conta."}


@router.post("/password-reset/request", status_code=202)
def request_password_reset(
    body: EmailInput,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    _rate_limit_request(request, RESET_PASSWORD)
    user = session.scalar(select(User).where(User.email == body.email))
    if user is not None and user.email_verified_at is not None:
        _, raw_token = _issue_action_token(
            session, user, RESET_PASSWORD, RESET_TOKEN_LIFETIME
        )
        session.commit()
        background_tasks.add_task(
            _deliver_without_disclosing_account_state, body.email, raw_token, RESET_PASSWORD
        )
    return {"message": "If the account exists, password reset instructions will be sent."}


@router.post("/password-reset/confirm")
def confirm_password_reset(
    body: PasswordResetInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    require_allowed_origin(request)
    response.headers["Cache-Control"] = "no-store"
    token = _valid_action_token(session, body.token, RESET_PASSWORD)
    if token is None:
        raise HTTPException(status_code=400, detail="reset token is invalid or expired")
    user = session.get(User, token.user_id)
    if user is None or user.email_verified_at is None:
        raise HTTPException(status_code=400, detail="reset token is invalid or expired")

    now = datetime.now(UTC)
    token.used_at = now
    user.password_hash = PASSWORD_HASHER.hash(body.new_password)
    active_tokens = session.scalars(
        select(AuthActionToken).where(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == RESET_PASSWORD,
            AuthActionToken.used_at.is_(None),
        )
    )
    for active_token in active_tokens:
        active_token.used_at = now
    active_sessions = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
    )
    for auth_session in active_sessions:
        auth_session.revoked_at = now
    session.commit()
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=get_settings().app_env.lower() not in {"development", "test"},
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Senha redefinida. Entre novamente."}


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
    if not valid or user is None or user.email_verified_at is None:
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
