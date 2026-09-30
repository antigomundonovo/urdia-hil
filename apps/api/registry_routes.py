"""Registry + audit read endpoints (Doc 02):
GET /api/v1/providers, GET /api/v1/capabilities, GET /api/v1/audit.

Read-only, workspace-scoped. Authorization is revalidated server-side
(Doc 08); when auth lands (open V1 ambiguity), the caller identity will
replace the explicit workspace_id parameter.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import Capability, Provider
from packages.domain.repositories import AuditRepository
from packages.shared.db import get_session

router = APIRouter(prefix="/api/v1")


def _workspace_or_404(workspace_id: UUID, session: Session):
    from packages.domain.models import Workspace

    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return workspace_id


@router.get("/providers")
def list_providers(
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _workspace_or_404(workspace_id, session)
    rows = session.scalars(select(Provider).order_by(Provider.key)).all()
    return {
        "providers": [
            {
                "id": str(p.id),
                "key": p.key,
                "name": p.name,
                "version": p.version,
                "health": p.health,
                "license": p.license,
                "last_verified_at": p.last_verified_at.isoformat() if p.last_verified_at else None,
            }
            for p in rows
        ]
    }


@router.get("/capabilities")
def list_capabilities(
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _workspace_or_404(workspace_id, session)
    rows = session.scalars(select(Capability).order_by(Capability.key)).all()
    return {
        "capabilities": [
            {
                "id": str(c.id),
                "key": c.key,
                "version": c.version,
                "status": c.status,
                "provider_id": str(c.provider_id) if c.provider_id else None,
                "fallback_provider_id": (
                    str(c.fallback_provider_id) if c.fallback_provider_id else None
                ),
                "quota": c.quota,
                "allowed_profiles": c.allowed_profiles,
            }
            for c in rows
        ]
    }


@router.get("/audit")
def list_audit(
    workspace_id: UUID = Query(...),
    profile_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    _workspace_or_404(workspace_id, session)
    events = AuditRepository(session).list_for_workspace(
        workspace_id, profile_id=profile_id, limit=limit
    )
    return {
        "audit": [
            {
                "id": str(e.id),
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": str(e.entity_id) if e.entity_id else None,
                "previous_state": e.previous_state,
                "new_state": e.new_state,
                "reason": e.reason,
                "provider": e.provider,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in events
        ]
    }
