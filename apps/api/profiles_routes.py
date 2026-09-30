"""Profiles endpoints (Doc 02): GET /api/v1/profiles (V1 read-only list;
POST/PATCH arrive with profile management). Scoped by workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import Profile
from packages.shared.db import get_session

router = APIRouter(prefix="/api/v1")


@router.get("/profiles")
def list_profiles(
    workspace_id: UUID | None = Query(None),
    session: Session = Depends(get_session),
):
    stmt = select(Profile).order_by(Profile.key)
    if workspace_id is not None:
        stmt = stmt.where(Profile.workspace_id == workspace_id)
    rows = session.scalars(stmt).all()
    return {
        "profiles": [
            {
                "id": str(p.id),
                "workspace_id": str(p.workspace_id),
                "key": p.key,
                "name": p.name,
                "language": p.language,
                "status": p.status,
            }
            for p in rows
        ]
    }
