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

from packages.domain.social import FactualityChallenge
from packages.research.social import (
    CHALLENGE_STATUSES,
    CHALLENGE_VERDICTS,
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
