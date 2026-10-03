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

from apps.api.auth import get_current_user
from packages.domain.editorial import ContentPackage, Draft
from packages.domain.models import Profile, User
from packages.domain.publishing import Publication
from packages.governance.audit import append_audit
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
    current_user: User = Depends(get_current_user),
):
    pub = _publication_scoped(session, publication_id, workspace_id)
    if pub.status != "FAILED":
        raise HTTPException(status_code=409, detail="only FAILED publications can be retried")
    previous_status = pub.status
    _apply_publication_status(pub, "PENDING")
    from packages.shared.execution_context import ExecutionContext

    append_audit(
        session,
        ctx=ExecutionContext(
            workspace_id=workspace_id,
            profile_id=pub.profile_id,
            actor_id=current_user.id,
        ),
        action="PUBLICATION_RETRIED",
        entity_type="publication",
        entity_id=pub.id,
        previous_state=previous_status,
        new_state="PENDING",
    )
    return {"id": str(pub.id), "status": pub.status}


@router.post("/publications/{publication_id}/manual-fallback")
def manual_fallback(
    publication_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Doc 14: platform down → manual export remains available; the content
    is never lost to a platform failure."""
    pub = _publication_scoped(session, publication_id, workspace_id)
    if pub.status in ("PUBLISHED", "MANUAL_FALLBACK"):
        raise HTTPException(status_code=409, detail=f"publication already {pub.status}")
    previous_status = pub.status
    _apply_publication_status(pub, "MANUAL_FALLBACK", error="platform unavailable — manual export")
    from packages.shared.execution_context import ExecutionContext

    append_audit(
        session,
        ctx=ExecutionContext(
            workspace_id=workspace_id,
            profile_id=pub.profile_id,
            actor_id=current_user.id,
        ),
        action="PUBLICATION_MANUAL_FALLBACK",
        entity_type="publication",
        entity_id=pub.id,
        previous_state=previous_status,
        new_state="MANUAL_FALLBACK",
        reason="platform unavailable — manual export",
    )
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
    current_user: User = Depends(get_current_user),
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
            reviewed_by=current_user.id,
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
    current_user: User = Depends(get_current_user),
):
    _profile_scoped(session, workspace_id, profile_id)
    from packages.domain.publishing import Rule

    rule = session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="rule not found")
    try:
        from packages.shared.execution_context import ExecutionContext

        active = LearningService(session).activate_rule(
            ExecutionContext(
                workspace_id=workspace_id,
                profile_id=profile_id,
                actor_id=current_user.id,
            ),
            rule,
        )
    except LearningError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return {"rule_id": str(active.id), "status": active.status}


# composition hint: OpportunityService imported for ctx consistency elsewhere
_ = OpportunityService


class ConfirmBody(BaseModel):
    remote_id: str | None = None


@router.post("/publications/{publication_id}/confirm")
def confirm_publication(
    publication_id: UUID,
    body: ConfirmBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """AMENDMENT-007: Confirm manual EXPORT/MANUAL publication was actually posted.

    Marks PENDING -> PUBLISHED with published_at and optional remote_id.
    Restricted to EXPORT/MANUAL method publications in PENDING status.
    Audited via existing audit trail.
    """
    pub = _publication_scoped(session, publication_id, workspace_id)

    # Only allow confirm for manual/export methods
    if pub.method not in ("EXPORT", "MANUAL"):
        raise HTTPException(
            status_code=409,
            detail=f"confirm only allowed for EXPORT/MANUAL publications, not {pub.method}",
        )

    if pub.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"confirm only allowed for PENDING publications, current status: {pub.status}",
        )

    from datetime import UTC, datetime

    previous_status = pub.status
    pub.status = "PUBLISHED"
    pub.published_at = datetime.now(UTC)
    if body.remote_id is not None:
        pub.remote_id = body.remote_id

    from packages.shared.execution_context import ExecutionContext

    append_audit(
        session,
        ctx=ExecutionContext(
            workspace_id=workspace_id,
            profile_id=pub.profile_id,
            actor_id=current_user.id,
        ),
        action="PUBLICATION_MANUAL_CONFIRMED",
        entity_type="publication",
        entity_id=pub.id,
        previous_state=previous_status,
        new_state="PUBLISHED",
        metadata={"remote_id": body.remote_id, "method": pub.method},
    )

    session.commit()
    return {"id": str(pub.id), "status": pub.status, "published_at": pub.published_at.isoformat()}


class PublishBody(BaseModel):
    profile_id: UUID
    public_image_urls: list[str] = Field(default_factory=list)
    public_video_url: str | None = None
    local_video_path: str | None = None
    privacy_level: str | None = None
    is_aigc: bool | None = None
    caption_override: str | None = None


@router.post("/publications/{publication_id}/publish")
def publish_via_api(
    publication_id: UUID,
    body: PublishBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Publish a PENDING publication through the platform's live API
    (AMENDMENT-014: first live adapter = Instagram).

    Human gate: this route IS the human action (Emenda 007 — nothing
    publishes by itself). Requires READY-gated content (publisher gate ran
    at export), a PENDING publication, and PUBLIC image URLs (the
    Instagram API fetches the image itself — local-first files cannot be
    fetched; use an asset host or the manual kit).
    """
    pub = _publication_scoped(session, publication_id, workspace_id)

    if pub.platform == "tiktok":
        if pub.status != "PENDING":
            raise HTTPException(
                status_code=409,
                detail=f"publish only allowed for PENDING publications, current: {pub.status}",
            )
        from pathlib import Path

        if not body.privacy_level:
            raise HTTPException(status_code=409, detail="TikTok privacy_level is required")
        if not body.local_video_path and not body.public_video_url:
            raise HTTPException(
                status_code=409, detail="TikTok requires a video path or public video URL"
            )
        video_path = body.local_video_path
        if video_path:
            from packages.shared.settings import get_settings

            root = Path(get_settings().asset_root).resolve()
            candidate = Path(video_path).resolve()
            if not candidate.is_relative_to(root):
                raise HTTPException(
                    status_code=409, detail="local video path must stay inside ASSET_ROOT"
                )
            video_path = str(candidate)
        package = session.get(ContentPackage, pub.content_package_id)
        if package is None or package.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="content package not found")
        draft = session.scalars(
            select(Draft)
            .where(Draft.content_package_id == package.id)
            .order_by(Draft.created_at.desc(), Draft.id.desc())
            .limit(1)
        ).first()
        if draft is None:
            raise HTTPException(status_code=409, detail="publication has no draft")
        caption = body.caption_override or (
            f"{draft.title}\n\n{draft.caption}" if draft.title else (draft.caption or "")
        )
        payload = {
            "format": "VIDEO",
            "caption": caption,
            "privacy_level": body.privacy_level,
            "is_aigc": body.is_aigc,
        }
        if video_path:
            payload["video_path"] = video_path
        else:
            payload["video_url"] = body.public_video_url
        from packages.providers.tiktok import TikTokPublisher, TikTokPublishError
        from packages.shared.execution_context import ExecutionContext

        try:
            result = TikTokPublisher().publish(
                payload, idempotency_key=pub.idempotency_key or str(pub.id)
            )
        except TikTokPublishError as err:
            raise HTTPException(status_code=409, detail=str(err)) from err
        pub.status = "PROCESSING"
        pub.method = "API"
        pub.remote_id = result.publish_id
        append_audit(
            session,
            ctx=ExecutionContext(
                workspace_id=workspace_id,
                profile_id=pub.profile_id,
                actor_id=current_user.id,
            ),
            action="PUBLICATION_API_SUBMITTED",
            entity_type="publication",
            entity_id=pub.id,
            new_state="PROCESSING",
            metadata={"platform": "tiktok", "publish_id": result.publish_id},
        )
        session.commit()
        return {"id": str(pub.id), "status": pub.status, "remote_id": pub.remote_id}

    if pub.platform != "instagram":
        raise HTTPException(
            status_code=409,
            detail=f"no live API adapter for platform {pub.platform} (manual kit available)",
        )
    if pub.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"publish only allowed for PENDING publications, current: {pub.status}",
        )

    # content: title+caption from the latest draft of the package
    package = session.get(ContentPackage, pub.content_package_id)
    if package is None or package.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="content package not found")
    draft = session.scalars(
        select(Draft)
        .where(Draft.content_package_id == package.id)
        .order_by(Draft.created_at.desc(), Draft.id.desc())
        .limit(1)
    ).first()
    if draft is None:
        raise HTTPException(status_code=409, detail="publication has no draft")

    caption = body.caption_override or (
        f"{draft.title}\n\n{draft.caption}" if draft.title else (draft.caption or "")
    )
    payload = {
        "format": package.format if package.format in ("PHOTO_POST", "CAROUSEL") else "PHOTO_POST",
        "caption": caption,
        "image_urls": body.public_image_urls,
    }

    from packages.providers.instagram import (
        InstagramPublisher,
        InstagramPublishError,
    )
    from packages.shared.execution_context import ExecutionContext

    publisher = InstagramPublisher()
    try:
        result = publisher.publish(payload, idempotency_key=pub.idempotency_key or str(pub.id))
    except InstagramPublishError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err

    pub.status = "PUBLISHED"
    pub.method = "API"
    pub.published_at = datetime.now(UTC)
    pub.remote_id = result.remote_id
    append_audit(
        session,
        ctx=ExecutionContext(
            workspace_id=workspace_id,
            profile_id=pub.profile_id,
            actor_id=current_user.id,
        ),
        action="PUBLICATION_API_PUBLISHED",
        entity_type="publication",
        entity_id=pub.id,
        new_state="PUBLISHED",
        metadata={
            "platform": pub.platform,
            "remote_id": result.remote_id,
            "permalink": result.permalink,
        },
    )
    session.commit()
    return {
        "id": str(pub.id),
        "status": pub.status,
        "method": "API",
        "remote_id": result.remote_id,
        "permalink": result.permalink,
    }


@router.post("/publications/{publication_id}/status")
def refresh_publication_status(
    publication_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    """Refresh asynchronous platform status after an API submission."""
    pub = _publication_scoped(session, publication_id, workspace_id)
    if pub.platform != "tiktok":
        raise HTTPException(
            status_code=409, detail="status refresh is currently available for TikTok"
        )
    if not pub.remote_id:
        raise HTTPException(status_code=409, detail="publication has no TikTok publish_id")

    from packages.providers.tiktok import TikTokPublisher, TikTokPublishError

    try:
        result = TikTokPublisher().status(pub.remote_id)
    except TikTokPublishError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err

    state = result["status"]
    if state == "PUBLISH_COMPLETE":
        pub.status = "PUBLISHED"
        post_ids = result.get("post_ids") or []
        if post_ids:
            pub.remote_id = str(post_ids[0])
        pub.published_at = datetime.now(UTC)
    elif state == "FAILED":
        pub.status = "FAILED"
        pub.error = result.get("fail_reason") or "TikTok publication failed"
    else:
        pub.status = "PROCESSING"

    session.commit()
    return {
        "id": str(pub.id),
        "status": pub.status,
        "remote_id": pub.remote_id,
        "platform_status": state,
        "error": pub.error,
    }
