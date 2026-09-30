"""Publications + Analytics + Learning endpoints (Doc 02):
GET /publications, POST /publications/{id}/retry, POST /publications/{id}/manual-fallback,
GET /analytics/overview, GET /analytics/publications/{id}, GET /analytics/comments,
GET /analytics/qualified-signals, GET /learning, POST /learning/experiments,
POST /learning/rules/{id}/review, POST /learning/rules/{id}/activate.

All workspace-scoped; server-side authorization revalidated (Doc 08).
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import Profile
from packages.domain.publishing import Publication
from packages.research.analytics import AnalyticsService
from packages.research.learning import LearningError, LearningService
from packages.research.opportunity import OpportunityService
from packages.shared.db import get_session

router = APIRouter(prefix="/api/v1")


def _profile_scoped(session: Session, workspace_id: UUID, profile_id: UUID) -> None:
    profile = session.scalars(
        select(Profile.id).where(
            Profile.id == profile_id,
            Profile.workspace_id == workspace_id,
        )
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found in workspace")


def _publication_scoped(session: Session, publication_id: UUID, workspace_id: UUID) -> Publication:
    pub = session.get(Publication, publication_id)
    if pub is None or pub.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="publication not found")
    return pub


def _ctx_for(session: Session, workspace_id: UUID, profile_id: UUID | None):
    from packages.shared.execution_context import ExecutionContext

    return ExecutionContext(workspace_id=workspace_id, profile_id=profile_id)


# --- publications -------------------------------------------------------------


@router.get("/publications")
def list_publications(
    workspace_id: UUID = Query(...),
    profile_id: UUID | None = Query(None),
    session: Session = Depends(get_session),
):
    if profile_id is not None:
        _profile_scoped(session, workspace_id, profile_id)
    stmt = select(Publication).where(Publication.workspace_id == workspace_id)
    if profile_id is not None:
        stmt = stmt.where(Publication.profile_id == profile_id)
    rows = session.scalars(stmt.order_by(Publication.created_at.desc())).all()
    return {
        "publications": [
            {
                "id": str(p.id),
                "content_package_id": str(p.content_package_id),
                "platform": p.platform,
                "method": p.method,
                "status": p.status,
                "remote_id": p.remote_id,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "idempotency_key": p.idempotency_key,
            }
            for p in rows
        ]
    }


class PublicationActionBody(BaseModel):
    profile_id: UUID


def _apply_publication_status(
    pub: Publication, status: str, error: str | None = None
) -> Publication:
    pub.status = status
    if error is not None:
        pub.error = error
    if status == "PUBLISHED":
        pub.published_at = datetime.now(UTC)
    return pub


@router.post("/publications/{publication_id}/retry")
def retry_publication(
    publication_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    pub = _publication_scoped(session, publication_id, workspace_id)
    if pub.status != "FAILED":
        raise HTTPException(status_code=409, detail="only FAILED publications can be retried")
    _apply_publication_status(pub, "PENDING")
    return {"id": str(pub.id), "status": pub.status}


@router.post("/publications/{publication_id}/manual-fallback")
def manual_fallback(
    publication_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    """Doc 14: platform down → manual export remains available; the content
    is never lost to a platform failure."""
    pub = _publication_scoped(session, publication_id, workspace_id)
    if pub.status in ("PUBLISHED", "MANUAL_FALLBACK"):
        raise HTTPException(status_code=409, detail=f"publication already {pub.status}")
    _apply_publication_status(pub, "MANUAL_FALLBACK", error="platform unavailable — manual export")
    return {"id": str(pub.id), "status": pub.status}


# --- analytics -------------------------------------------------------------------


@router.get("/analytics/overview")
def analytics_overview(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    return AnalyticsService(session).overview(workspace_id, profile_id)


@router.get("/analytics/publications/{publication_id}")
def analytics_publication(
    publication_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    pub = _publication_scoped(session, publication_id, workspace_id)
    return AnalyticsService(session).publication_snapshot(
        _ctx_for(session, workspace_id, pub.profile_id), pub
    )


class MetricsBody(BaseModel):
    profile_id: UUID
    values: dict[str, int] = Field(min_length=1)


@router.post("/analytics/publications/{publication_id}/collect")
def collect_metrics(
    publication_id: UUID,
    body: MetricsBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    """Append-only collection point (Doc 15): each call creates new events."""
    pub = _publication_scoped(session, publication_id, workspace_id)
    if body.profile_id != pub.profile_id:
        raise HTTPException(status_code=404, detail="publication not found")
    count = AnalyticsService(session).record_metrics(
        _ctx_for(session, workspace_id, pub.profile_id), pub, body.values
    )
    return {"collected": count, "publication_id": str(pub.id)}


class CommentBody(BaseModel):
    text: str
    author_ref: str | None = None


@router.get("/analytics/comments")
def analytics_comments(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    rows = AnalyticsService(session).list_comments(workspace_id, profile_id, limit)
    return {
        "comments": [
            {
                "id": str(c.id),
                "intent": c.intent,
                "qualified_signal": c.qualified_signal,
                "text": c.text,
            }
            for c in rows
        ]
    }


@router.get("/analytics/qualified-signals")
def analytics_qualified_signals(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    rows = AnalyticsService(session).qualified_signals(workspace_id, profile_id)
    return {
        "signals": [
            {
                "id": str(c.id),
                "signal": c.qualified_signal,
                "intent": c.intent,
                "text": c.text,
            }
            for c in rows
        ]
    }


# --- learning ---------------------------------------------------------------------


@router.get("/learning")
def learning_state(
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    return LearningService(session).list_state(workspace_id, profile_id)


class ExperimentBody(BaseModel):
    hypothesis: str
    variants: dict[str, dict] = Field(min_length=2)


@router.post("/learning/experiments")
def create_experiment(
    body: ExperimentBody,
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    try:
        experiment = LearningService(session).create_experiment(
            _ctx_for(session, workspace_id, profile_id),
            hypothesis=body.hypothesis,
            variants=body.variants,
        )
    except LearningError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return {"experiment_id": str(experiment.id), "status": experiment.status}


class RuleBody(BaseModel):
    statement: str
    origin_experiment_id: UUID | None = None


@router.post("/learning/rules")
def propose_rule(
    body: RuleBody,
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    rule = LearningService(session).propose_rule(
        _ctx_for(session, workspace_id, profile_id),
        statement=body.statement,
        origin_experiment_id=body.origin_experiment_id,
    )
    return {"rule_id": str(rule.id), "status": rule.status}


class ReviewBody(BaseModel):
    reviewed_by: UUID | None = None
    notes: str | None = None


@router.post("/learning/rules/{rule_id}/review")
def review_rule(
    rule_id: UUID,
    body: ReviewBody,
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    from packages.domain.publishing import Rule

    rule = session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="rule not found")
    try:
        reviewed = LearningService(session).review_rule(
            _ctx_for(session, workspace_id, profile_id),
            rule,
            reviewed_by=body.reviewed_by,
            notes=body.notes,
        )
    except LearningError as err:
        status_code = 404 if "not found" in str(err) else 409
        raise HTTPException(status_code=status_code, detail=str(err)) from err
    return {"rule_id": str(reviewed.id), "status": reviewed.status}


@router.post("/learning/rules/{rule_id}/activate")
def activate_rule(
    rule_id: UUID,
    workspace_id: UUID = Query(...),
    profile_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    from packages.domain.publishing import Rule

    rule = session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="rule not found")
    try:
        active = LearningService(session).activate_rule(
            _ctx_for(session, workspace_id, profile_id), rule
        )
    except LearningError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return {"rule_id": str(active.id), "status": active.status}


# composition hint: OpportunityService imported for ctx consistency elsewhere
_ = OpportunityService
