"""Auxiliary memory API (V2.2 Hermes, Doc 05 §Memory). Session-authenticated;
workspace membership is enforced here because workspace_id arrives in the
body (router-level dependency expects it as a query param)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from packages.domain.models import User, WorkspaceMember
from packages.research.memory import MemoryError, MemoryService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

router = APIRouter(prefix="/api/v1/memory")


def _require_membership(session: Session, workspace_id: UUID, user: User) -> None:
    membership = session.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="workspace not found")


class MemoryIn(BaseModel):
    workspace_id: UUID
    profile_id: UUID | None = None
    kind: str
    content: str
    origin: dict | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _ctx(payload: MemoryIn, user_id: UUID) -> ExecutionContext:
    return ExecutionContext(
        workspace_id=payload.workspace_id,
        profile_id=payload.profile_id,
        actor_id=user_id,
    )


def _out(entry) -> dict:
    return {
        "id": str(entry.id),
        "kind": entry.kind,
        "content": entry.content,
        "origin": entry.origin,
        "confidence": entry.confidence,
        "status": entry.status,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.post("", status_code=201)
def remember(
    payload: MemoryIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _require_membership(session, payload.workspace_id, current_user)
    try:
        entry = MemoryService(session).remember(
            _ctx(payload, current_user.id),
            kind=payload.kind,
            content=payload.content,
            origin=payload.origin,
            confidence=payload.confidence,
            actor_id=current_user.id,
            profile_id=payload.profile_id,
        )
        session.commit()
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _out(entry)


@router.get("")
def list_memories(
    workspace_id: UUID,
    kind: str | None = None,
    profile_id: UUID | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _require_membership(session, workspace_id, current_user)
    try:
        entries = MemoryService(session).list_active(
            ExecutionContext(workspace_id=workspace_id),
            kind=kind,
            profile_id=profile_id,
        )
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_out(e) for e in entries]


class SupersedeIn(BaseModel):
    workspace_id: UUID
    kind: str
    content: str
    origin: dict | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@router.post("/{memory_id}/supersede", status_code=201)
def supersede(
    memory_id: UUID,
    payload: SupersedeIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _require_membership(session, payload.workspace_id, current_user)
    try:
        entry = MemoryService(session).supersede(
            ExecutionContext(workspace_id=payload.workspace_id, actor_id=current_user.id),
            memory_id,
            kind=payload.kind,
            content=payload.content,
            origin=payload.origin,
            confidence=payload.confidence,
            actor_id=current_user.id,
        )
        session.commit()
    except MemoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(entry)


@router.post("/{memory_id}/archive")
def archive(
    memory_id: UUID,
    workspace_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _require_membership(session, workspace_id, current_user)
    try:
        entry = MemoryService(session).archive(
            ExecutionContext(workspace_id=workspace_id, actor_id=current_user.id),
            memory_id,
        )
        session.commit()
    except MemoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(entry)
