"""Social intelligence endpoints (AMENDMENT-2026-10-02-013, contract §11):
POST /social/challenges, GET /social/challenges, POST /social/challenges/{id}/research,
POST /social/challenges/{id}/review, POST /social/challenges/{id}/dismiss.

All workspace/profile-scoped; server-side authorization revalidated (Doc 08).
A comment is never evidence by itself — evidence only via registered sources.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from packages.domain.social import FactualityChallenge, AudienceDemand, AudiencePulse
from packages.research.social import (
    CHALLENGE_STATUSES,
    CHALLENGE_VERDICTS,
    INBOX_STATUSES,
    SocialError,
    SocialIntelligenceService,
)
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

router = APIRouter(prefix="/api/v1")


def _ctx(workspace_id: UUID, profile_id: UUID) -> ExecutionContext:
    return ExecutionContext(workspace_id=workspace_id, profile_id=profile_id)


def _challenge_out(challenge: FactualityChallenge) -> dict:
    return {
        "id": str(challenge.id),
        "comment_id": str(challenge.comment_id),
        "statement": challenge.statement,
        "claim_id": str(challenge.claim_id) if challenge.claim_id else None,
        "status": challenge.status,
        "verdict": challenge.verdict,
        "verdict_reason": challenge.verdict_reason,
        "researched_at": (
            challenge.researched_at.isoformat() if challenge.researched_at else None
        ),
        "reviewed_at": (
            challenge.reviewed_at.isoformat() if challenge.reviewed_at else None
        ),
        "created_at": challenge.created_at.isoformat(),
    }


class ChallengeCreate(BaseModel):
    profile_id: UUID
    comment_id: UUID
    statement: str = Field(min_length=3, max_length=2000)


class ChallengeReview(BaseModel):
    profile_id: UUID
    verdict: str
    reason: str | None = Field(default=None, max_length=2000)


class ChallengeDismiss(BaseModel):
    profile_id: UUID
    reason: str = Field(min_length=3, max_length=2000)


@router.post("/social/challenges")
def create_challenge(
    payload: ChallengeCreate,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    try:
        challenge = service.create_challenge(
            _ctx(workspace_id, payload.profile_id),
            comment_id=payload.comment_id,
            statement=payload.statement,
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _challenge_out(challenge)


@router.get("/social/challenges")
def list_challenges(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    status: str | None = Query(None),
    session: Session = Depends(get_session),
):
    if status and status not in CHALLENGE_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    service = SocialIntelligenceService(session)
    challenges = service.list_challenges(_ctx(workspace_id, profile_id), status)
    return [_challenge_out(c) for c in challenges]


@router.post("/social/challenges/{challenge_id}/research")
def research_challenge(
    challenge_id: UUID,
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    try:
        challenge = service.research_challenge(
            _ctx(workspace_id, profile_id), challenge_id
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _challenge_out(challenge)


@router.post("/social/challenges/{challenge_id}/review")
def review_challenge(
    challenge_id: UUID,
    payload: ChallengeReview,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    if payload.verdict not in CHALLENGE_VERDICTS:
        raise HTTPException(status_code=422, detail=f"invalid verdict: {payload.verdict}")
    service = SocialIntelligenceService(session)
    try:
        challenge = service.review_challenge(
            _ctx(workspace_id, payload.profile_id),
            challenge_id,
            verdict=payload.verdict,
            reason=payload.reason,
            reviewed_by=None,  # actor attribution via audit context
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _challenge_out(challenge)


@router.post("/social/challenges/{challenge_id}/dismiss")
def dismiss_challenge(
    challenge_id: UUID,
    payload: ChallengeDismiss,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    try:
        challenge = service.dismiss_challenge(
            _ctx(workspace_id, payload.profile_id),
            challenge_id,
            reason=payload.reason,
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _challenge_out(challenge)

# --- social inbox endpoints ------------------------------------------------

class InboxItemCreate(BaseModel):
    profile_id: UUID
    comment_id: UUID | None = None
    item_type: str = "COMMENT"

class InboxItemStatusUpdate(BaseModel):
    profile_id: UUID
    status: str

class InboxItemAssign(BaseModel):
    profile_id: UUID
    user_id: UUID | None = None

def _inbox_item_out(item) -> dict:
    return {
        "id": str(item.id),
        "comment_id": str(item.comment_id) if item.comment_id else None,
        "item_type": item.item_type,
        "status": item.status,
        "assigned_to": str(item.assigned_to) if item.assigned_to else None,
        "suggested_reply": item.suggested_reply,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }

@router.post("/social/inbox")
def create_inbox_item(
    payload: InboxItemCreate,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    try:
        item = service.create_inbox_item(
            _ctx(workspace_id, payload.profile_id),
            item_type=payload.item_type,
            comment_id=payload.comment_id,
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _inbox_item_out(item)

@router.get("/social/inbox")
def list_inbox_items(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    status: str | None = Query(None),
    session: Session = Depends(get_session),
):
    if status and status not in ("UNREAD", "OPEN", "RESOLVED", "IGNORED"):
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    service = SocialIntelligenceService(session)
    items = service.list_inbox_items(_ctx(workspace_id, profile_id), status)
    return [_inbox_item_out(i) for i in items]

INBOX_STATUSES = ("UNREAD", "OPEN", "RESOLVED", "IGNORED")

@router.post("/social/inbox/{item_id}/status")
def update_inbox_item_status(
    item_id: UUID,
    payload: InboxItemStatusUpdate,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    if payload.status not in INBOX_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {payload.status}")
    service = SocialIntelligenceService(session)
    try:
        item = service.update_inbox_item_status(
            _ctx(workspace_id, payload.profile_id),
            item_id,
            status=payload.status,
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _inbox_item_out(item)

@router.post("/social/inbox/{item_id}/assign")
def assign_inbox_item(
    item_id: UUID,
    payload: InboxItemAssign,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    try:
        item = service.assign_inbox_item(
            _ctx(workspace_id, payload.profile_id),
            item_id,
            user_id=payload.user_id,
        )
        session.commit()
    except SocialError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _inbox_item_out(item)

@router.get("/social/audience/demand")
def list_audience_demand(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    demands = service.list_audience_demand(_ctx(workspace_id, profile_id))
    return [
        {
            "id": str(d.id),
            "summary": d.summary,
            "unique_people_count": d.unique_people_count,
            "growth": d.growth,
            "confidence": d.confidence,
        }
        for d in demands
    ]

@router.get("/social/audience/pulse")
def get_audience_pulse(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    service = SocialIntelligenceService(session)
    pulse = service.get_latest_audience_pulse(_ctx(workspace_id, profile_id))
    if not pulse:
        raise HTTPException(status_code=404, detail="No pulse data found")
    return {
        "id": str(pulse.id),
        "sentiment_score": pulse.sentiment_score,
        "topic_clusters": pulse.topic_clusters,
    }
