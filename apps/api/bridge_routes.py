"""Studio⇄HIL bridge (Emenda 002 / contrato §10, fase V2.1).

Two disjoint surfaces:
- Client management (human, session-cookie auth): create/list/revoke
  machine API keys scoped to a workspace. The raw key is returned once.
- Export (machine, Bearer key): read-only demand data for the Studio.
  The allowlist is this router: a machine key can never reach any other
  router because it never passes ``get_current_user``.
"""

from datetime import UTC, datetime
from secrets import token_hex
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user, require_allowed_origin, token_digest
from packages.domain.models import AuditEvent, MachineClient, User
from packages.domain.social import AudienceDemand
from packages.shared.db import get_session

MACHINE_KEY_PREFIX = "urdia_mk_"

router = APIRouter(prefix="/api/v1/bridge")


def _resolve_machine_client(
    authorization: str,
    session: Session,
    workspace_id: UUID,
) -> MachineClient:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="machine key required")
    raw = authorization.removeprefix("Bearer ").strip()
    if not raw.startswith(MACHINE_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="machine key required")
    client = session.scalar(
        select(MachineClient).where(MachineClient.key_hash == token_digest(raw))
    )
    if client is None or client.revoked_at is not None:
        raise HTTPException(status_code=401, detail="machine key required")
    if client.workspace_id != workspace_id:
        # Never disclose other workspaces' existence to a valid key.
        raise HTTPException(status_code=404, detail="workspace not found")
    client.last_used_at = datetime.now(UTC)
    return client


class MachineClientCreate(BaseModel):
    workspace_id: UUID
    name: str


def _require_membership(session: Session, workspace_id: UUID, user: User) -> None:
    from packages.domain.models import WorkspaceMember

    membership = session.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="workspace not found")


@router.post("/clients", status_code=201)
def create_machine_client(
    payload: MachineClientCreate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    require_allowed_origin(request)
    _require_membership(session, payload.workspace_id, current_user)
    raw_key = MACHINE_KEY_PREFIX + token_hex(24)
    client = MachineClient(
        workspace_id=payload.workspace_id,
        name=payload.name,
        key_hash=token_digest(raw_key),
        created_by=current_user.id,
    )
    session.add(client)
    session.flush()
    session.add(
        AuditEvent(
            workspace_id=payload.workspace_id,
            actor_id=current_user.id,
            action="MACHINE_CLIENT_CREATED",
            entity_type="machine_client",
            entity_id=client.id,
            metadata_={"name": payload.name},
        )
    )
    session.commit()
    return {
        "id": str(client.id),
        "name": client.name,
        "api_key": raw_key,  # shown exactly once
    }


@router.get("/clients")
def list_machine_clients(
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _require_membership(session, workspace_id, current_user)
    clients = session.scalars(
        select(MachineClient)
        .where(MachineClient.workspace_id == workspace_id)
        .order_by(MachineClient.created_at.desc())
    ).all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "revoked": c.revoked_at is not None,
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in clients
    ]


@router.delete("/clients/{client_id}", status_code=204)
def revoke_machine_client(
    client_id: UUID,
    request: Request,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if request is not None:
        require_allowed_origin(request)
    _require_membership(session, workspace_id, current_user)
    client = session.scalar(
        select(MachineClient).where(
            MachineClient.id == client_id,
            MachineClient.workspace_id == workspace_id,
        )
    )
    if client is None:
        raise HTTPException(status_code=404, detail="machine client not found")
    if client.revoked_at is None:
        client.revoked_at = datetime.now(UTC)
        session.add(
            AuditEvent(
                workspace_id=workspace_id,
                actor_id=current_user.id,
                action="MACHINE_CLIENT_REVOKED",
                entity_type="machine_client",
                entity_id=client.id,
            )
        )
        session.commit()


@router.get("/demand")
def export_audience_demand(
    request: Request,
    workspace_id: UUID = Query(...),
    profile_id: UUID | None = Query(None),
    session: Session = Depends(get_session),
):
    _resolve_machine_client(request.headers.get("authorization", ""), session, workspace_id)
    stmt = (
        select(AudienceDemand)
        .where(AudienceDemand.workspace_id == workspace_id)
        .order_by(AudienceDemand.created_at.desc())
    )
    if profile_id is not None:
        stmt = stmt.where(AudienceDemand.profile_id == profile_id)
    demands = session.scalars(stmt).all()
    # Contract §10: structured demand — the exact fields the Studio consumes.
    return [
        {
            "id": str(d.id),
            "profile_id": str(d.profile_id) if d.profile_id else None,
            "summary": d.summary,
            "evidence": d.evidence,
            "unique_people_count": d.unique_people_count,
            "growth": d.growth,
            "engagement": d.engagement,
            "platforms": d.platforms,
            "confidence": d.confidence,
            "editorial_fit": d.editorial_fit,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in demands
    ]
