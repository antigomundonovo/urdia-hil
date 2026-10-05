"""Opaque-cookie authentication and workspace membership enforcement."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import AuthSession, User, WorkspaceMember
from packages.shared.db import get_session
from packages.shared.settings import get_settings

SESSION_COOKIE = "urdia_session"


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="authentication required")
    auth_session = session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_digest(session_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    if auth_session is None:
        raise HTTPException(status_code=401, detail="authentication required")
    user = session.get(User, auth_session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def require_workspace_access(
    request: Request,
    workspace_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        require_allowed_origin(request)
    membership = session.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="workspace not found")


def require_allowed_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin not in get_settings().cors_origin_list:
        raise HTTPException(status_code=403, detail="request origin not allowed")
