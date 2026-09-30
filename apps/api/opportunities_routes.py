"""Opportunities endpoints (Doc 02):
GET /api/v1/profiles/{profile_id}/opportunities, GET /api/v1/opportunities/{id}.

Workspace-scoped; the detail response includes the Why Panel data (Doc 06).
Content/QC actions live in content_routes.
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.editorial import Opportunity, OpportunityClaim
from packages.domain.knowledge import Claim
from packages.domain.models import Profile
from packages.research.opportunity import OpportunityService
from packages.shared.db import get_session
from packages.shared.settings import get_settings

router = APIRouter(prefix="/api/v1")


def _payload(opp: Opportunity) -> dict:
    return {
        "id": str(opp.id),
        "workspace_id": str(opp.workspace_id),
        "profile_id": str(opp.profile_id),
        "story_id": str(opp.story_id) if opp.story_id else None,
        "title": opp.title,
        "description": opp.description,
        "why_now": opp.why_now,
        "why_profile": opp.why_profile,
        "editorial_analysis": opp.editorial_analysis,
        "risk_analysis": opp.risk_analysis,
        "decision": opp.decision,
        "decision_reason": opp.decision_reason,
        "priority": opp.priority,
        "state": opp.state,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
    }


@router.get("/profiles/{profile_id}/opportunities")
def list_opportunities(
    profile_id: UUID,
    workspace_id: UUID = Query(...),
    state: str | None = Query(None),
    session: Session = Depends(get_session),
):
    # profile membership revalidated server-side (Doc 08)
    profile = session.get(Profile, profile_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="profile not found in workspace")
    rows = OpportunityService(session).list_for_profile(workspace_id, profile_id, state=state)
    return {"opportunities": [_payload(o) for o in rows]}


class RejectBody(BaseModel):
    reason: str


@router.post("/opportunities/{opportunity_id}/run-qc")
def run_qc_for_opportunity(
    opportunity_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    """Runs QC on the opportunity's latest content package (convenience over
    POST /content/{package_id}/run-qc)."""
    from packages.domain.editorial import ContentPackage
    from packages.research.content import ContentService

    opp = OpportunityService(session).get_scoped(opportunity_id, workspace_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    package = session.scalars(
        select(ContentPackage)
        .where(ContentPackage.opportunity_id == opp.id)
        .order_by(ContentPackage.created_at.desc())
        .limit(1)
    ).first()
    if package is None:
        raise HTTPException(status_code=404, detail="opportunity has no content package")
    ctx = OpportunityService(session).get_session_ctx(opp)
    return ContentService(
        session,
        asset_root=Path(get_settings().asset_root),
    ).run_qc(ctx, package)


@router.post("/opportunities/{opportunity_id}/approve")
def approve_opportunity(
    opportunity_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    from packages.research.content import ContentService, PublicationBlocked

    opp = OpportunityService(session).get_scoped(opportunity_id, workspace_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    ctx = OpportunityService(session).get_session_ctx(opp)
    try:
        ContentService(session).approve(ctx, opp)
    except PublicationBlocked as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return {"opportunity_id": str(opp.id), "state": opp.state}


@router.post("/opportunities/{opportunity_id}/reject")
def reject_opportunity(
    opportunity_id: UUID,
    body: RejectBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    from packages.research.content import ContentService

    opp = OpportunityService(session).get_scoped(opportunity_id, workspace_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    ctx = OpportunityService(session).get_session_ctx(opp)
    ContentService(session).reject(ctx, opp, reason=body.reason)
    return {"opportunity_id": str(opp.id), "state": opp.state}


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    opp = OpportunityService(session).get_scoped(opportunity_id, workspace_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    payload = _payload(opp)
    claims = session.scalars(
        select(Claim)
        .join(OpportunityClaim, OpportunityClaim.ref_id == Claim.id)
        .where(
            OpportunityClaim.opportunity_id == opp.id,
            OpportunityClaim.workspace_id == workspace_id,
            Claim.workspace_id == workspace_id,
            Claim.profile_id == opp.profile_id,
        )
        .order_by(Claim.created_at, Claim.id)
    )
    payload["claims"] = [
        {
            "id": str(claim.id),
            "text": (
                claim.editorial_wording
                or claim.normalized_text
                or f"{claim.subject or ''} {claim.predicate or ''} {claim.object or ''}".strip()
            ),
            "status": claim.status.value if hasattr(claim.status, "value") else str(claim.status),
        }
        for claim in claims
    ]
    return payload
