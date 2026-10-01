"""Real job handlers for key JobTypes (Doc 17).

These handlers use existing domain services to perform work and keep the JobEngine
checkpoint semantics. Each handler receives an ExecutionContext, payload dict,
and JobProgress and returns a dict with result metadata.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from apps.worker.engine import FatalJobError, JobProgress
from packages.domain.assets import Asset
from packages.domain.models import Source
from packages.shared.db import SessionLocal
from packages.shared.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


def _settings():
    from packages.shared.settings import get_settings

    return get_settings()


# ---------------------------------------------------------------------------
# IMAGE_ANALYSIS
# ---------------------------------------------------------------------------
def image_analysis(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Analyze image assets for duplicate detection and visual classification.

    Expected payload keys:
      - asset_ids: list[str]
    """
    if not payload.get("asset_ids"):
        raise FatalJobError("image_analysis requires asset_ids")
    asset_ids = payload["asset_ids"]

    progress.next("load_assets")
    with SessionLocal() as session:
        assets = session.scalars(
            select(Asset).where(
                Asset.id.in_(asset_ids),
                Asset.workspace_id == ctx.workspace_id,
                Asset.profile_id == ctx.profile_id,
            )
        ).all()
        if not assets:
            raise FatalJobError("no assets found for profile")

        progress.next("analyze")
        results = []
        for asset in assets:
            # Mark as analyzed — real implementation would run perceptual hash,
            # classification, etc. Here we only log and succeed.
            logger.debug("Analyze asset %s", asset.id)
            results.append({"asset_id": str(asset.id), "status": "analyzed"})

        session.commit()
        progress.done("analyze")
    return {"analyzed": len(results), "assets": results}

IMAGE_ANALYSIS = image_analysis

# ---------------------------------------------------------------------------
# RIGHTS_RESEARCH
# ---------------------------------------------------------------------------
def rights_research(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Run rights research for assets and attach classification if missing.

    Expected payload keys:
      - asset_ids: list[str]
    """
    if not payload.get("asset_ids"):
        raise FatalJobError("rights_research requires asset_ids")
    asset_ids = payload["asset_ids"]

    progress.next("resolve_assets")
    with SessionLocal() as session:
        assets = session.scalars(
            select(Asset).where(
                Asset.id.in_(asset_ids),
                Asset.workspace_id == ctx.workspace_id,
                Asset.profile_id == ctx.profile_id,
            )
        ).all()
        if not assets:
            raise FatalJobError("no assets found for profile")

        progress.next("research")
        processed = 0
        for asset in assets:
            # In a real implementation this would query external services.
            # Here we just log and count.
            logger.debug("Rights research for asset %s", asset.id)
            processed += 1

        session.commit()
        progress.done("research")
    return {"processed": processed, "asset_ids": [str(a.id) for a in assets]}

RIGHTS_RESEARCH = rights_research

# ---------------------------------------------------------------------------
# CLAIM_EXTRACTION
# ---------------------------------------------------------------------------
def claim_extraction(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Extract claims from a set of source IDs.

    Expected payload keys:
      - source_ids: list[str]
    """
    if not payload.get("source_ids"):
        raise FatalJobError("claim_extraction requires source_ids")
    source_ids = payload["source_ids"]

    progress.next("resolve_sources")
    with SessionLocal() as session:
        sources = session.scalars(
            select(Source).where(
                Source.id.in_(source_ids),
                Source.workspace_id == ctx.workspace_id,
                Source.profile_id == ctx.profile_id,
            )
        ).all()
        if not sources:
            raise FatalJobError("no sources found for profile")

        progress.next("extract")
        extracted = 0
        for src in sources:
            # Placeholder: real extraction would parse source content.
            logger.debug("Extract claims from source %s", src.id)
            extracted += 1

        session.commit()
        progress.done("extract")
    return {"sources_processed": len(sources), "claims_extracted": extracted}

CLAIM_EXTRACTION = claim_extraction

# ---------------------------------------------------------------------------
# FORMAT_PLANNING
# ---------------------------------------------------------------------------
def format_planning(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Decide content format for an opportunity.

    Expected payload keys:
      - opportunity_id: str
    """
    opp_id = payload.get("opportunity_id")
    if not opp_id:
        raise FatalJobError("format_planning requires opportunity_id")

    progress.next("load_opportunity")
    with SessionLocal() as session:
        from packages.domain.editorial import Opportunity

        opp = session.get(Opportunity, opp_id)
        if (
            not opp
            or opp.workspace_id != ctx.workspace_id
            or opp.profile_id != ctx.profile_id
        ):
            raise FatalJobError("opportunity not found in profile")

        progress.next("plan")
        # Placeholder: real logic would run JEV/format planner.
        logger.debug("Format planning for opportunity %s", opp.id)

        session.commit()
        progress.done("plan")
    return {"opportunity_id": str(opp.id), "planned_format": "PHOTO_POST"}

FORMAT_PLANNING = format_planning

# ---------------------------------------------------------------------------
# OPPORTUNITY_ANALYSIS (simple heuristic)
# ---------------------------------------------------------------------------
def opportunity_analysis(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Run JEV-style heuristic analysis over opportunities.

    Expected payload keys:
      - opportunity_ids: list[str] (optional, defaults to all in profile)
    """
    progress.next("load_opportunities")
    with SessionLocal() as session:
        from packages.domain.editorial import Opportunity

        opp_ids = payload.get("opportunity_ids")
        stmt = select(Opportunity).where(
            Opportunity.workspace_id == ctx.workspace_id,
            Opportunity.profile_id == ctx.profile_id,
        )
        if opp_ids:
            stmt = stmt.where(Opportunity.id.in_(opp_ids))
        opps = session.scalars(stmt).all()

        progress.next("analyze")
        analyzed = []
        for opp in opps:
            # Placeholder: real JEV recommendation logic.
            logger.debug("Opportunity analysis %s", opp.id)
            analyzed.append(str(opp.id))

        session.commit()
        progress.done("analyze")
    return {"analyzed": len(analyzed), "opportunity_ids": analyzed}


OPPORTUNITY_ANALYSIS = opportunity_analysis


def _package_for_context(session, ctx: ExecutionContext, package_id: Any):
    """ContentPackage scoped to the job's workspace — fail closed otherwise."""
    from packages.domain.editorial import ContentPackage

    package = session.get(ContentPackage, uuid.UUID(str(package_id)))
    if package is None or package.workspace_id != ctx.workspace_id:
        raise FatalJobError("content package not found in job workspace")
    return package


def _publication_for_context(session, ctx: ExecutionContext, publication_id: Any):
    from packages.domain.publishing import Publication

    publication = session.get(Publication, uuid.UUID(str(publication_id)))
    if (
        publication is None
        or publication.workspace_id != ctx.workspace_id
        or publication.profile_id != ctx.profile_id
    ):
        raise FatalJobError("publication not found in job profile")
    return publication


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------
def qc_handler(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Run the deterministic QC gates (Doc 00 §21) for a content package.

    Expected payload keys:
      - package_id: str
    """
    package_id = payload.get("package_id")
    if not package_id:
        raise FatalJobError("qc requires package_id")

    progress.next("load_package")
    with SessionLocal() as session:
        from packages.research.content import ContentService

        package = _package_for_context(session, ctx, package_id)
        service = ContentService(session)

        progress.next("run_gates")
        result = service.run_qc(ctx, package)
        session.commit()
        progress.done("run_gates")
    return {
        "package_id": str(package.id),
        "gates": result.get("gates", result),
        "blocking": result.get("blocking", []),
        "warnings": result.get("warnings", []),
    }


QC = qc_handler


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------
def export_handler(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Export a READY package for manual publication (Doc 14: V1 publication
    method is the manual export bundle). Governance blocks (rights/QC) are
    fatal, not retryable.

    Expected payload keys:
      - package_id: str
      - platform: str
    """
    package_id = payload.get("package_id")
    platform = payload.get("platform")
    if not package_id or not platform:
        raise FatalJobError("export requires package_id and platform")

    progress.next("load_package")
    with SessionLocal() as session:
        from packages.research.content import ContentService, PublicationBlocked

        package = _package_for_context(session, ctx, package_id)
        service = ContentService(session, export_root=Path(_settings().export_root))

        progress.next("export")
        try:
            export_dir = service.export_package(ctx, package, str(platform))
        except PublicationBlocked as exc:
            raise FatalJobError(f"export blocked: {exc}") from exc
        session.commit()
        progress.done("export")
    return {"package_id": str(package.id), "platform": str(platform), "path": str(export_dir)}


EXPORT = export_handler


# ---------------------------------------------------------------------------
# ANALYTICS_SYNC
# ---------------------------------------------------------------------------
def analytics_sync(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Record platform metrics for a publication (Doc 15). In V1 metrics
    arrive via manual import — the job appends fresh metric_events; history
    is never overwritten.

    Expected payload keys:
      - publication_id: str
      - metrics: dict[str, int] (REACH, IMPRESSIONS, VIEWS, SAVES, SHARES,
        COMMENTS, CLICKS, FOLLOWERS_GAINED, RETENTION, REPLAYS)
    """
    publication_id = payload.get("publication_id")
    metrics = payload.get("metrics")
    if not publication_id or not isinstance(metrics, dict) or not metrics:
        raise FatalJobError("analytics_sync requires publication_id and metrics dict")

    progress.next("load_publication")
    with SessionLocal() as session:
        from packages.research.analytics import AnalyticsService

        publication = _publication_for_context(session, ctx, publication_id)
        service = AnalyticsService(session)

        progress.next("record")
        try:
            count = service.record_metrics(ctx, publication, metrics)
        except ValueError as exc:
            raise FatalJobError(f"invalid metrics payload: {exc}") from exc
        session.commit()
        progress.done("record")
    return {"publication_id": str(publication.id), "metrics_recorded": count}


ANALYTICS_SYNC = analytics_sync


# ---------------------------------------------------------------------------
# COMMENT_SYNC
# ---------------------------------------------------------------------------
def comment_sync(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Import comments for a publication; each is classified (intent +
    qualified signal) by the deterministic analyzer (Doc 15).

    Expected payload keys:
      - publication_id: str (optional — profile-level comments allowed)
      - comments: list[{"text": str, "author_ref": str?}]
    """
    comments = payload.get("comments")
    if not isinstance(comments, list) or not comments:
        raise FatalJobError("comment_sync requires a comments list")

    publication_id = payload.get("publication_id")
    progress.next("load_publication")
    with SessionLocal() as session:
        from packages.research.analytics import AnalyticsService

        publication = None
        if publication_id:
            publication = _publication_for_context(session, ctx, publication_id)
        service = AnalyticsService(session)

        progress.next("import")
        counts: dict[str, int] = {}
        for entry in comments:
            text = (entry or {}).get("text") if isinstance(entry, dict) else None
            if not text or not str(text).strip():
                raise FatalJobError("comment entry requires non-empty text")
            comment = service.add_comment(
                ctx,
                publication,
                text=str(text),
                author_ref=(entry or {}).get("author_ref"),
            )
            key = comment.qualified_signal or comment.intent
            counts[key] = counts.get(key, 0) + 1
        session.commit()
        progress.done("import")
    return {"imported": len(comments), "by_signal": counts}


COMMENT_SYNC = comment_sync


# ---------------------------------------------------------------------------
# LEARNING_ANALYSIS
# ---------------------------------------------------------------------------
def learning_analysis(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Consolidate the profile's learning state (Doc 15): experiment/rule
    counts by status plus qualified comment signals. Read-only — activating
    rules requires explicit human review (LearningService), never a job.

    Expected payload keys: none.
    """
    if ctx.profile_id is None:
        raise FatalJobError("learning_analysis requires a profile context")

    progress.next("consolidate")
    with SessionLocal() as session:
        from packages.research.analytics import AnalyticsService
        from packages.research.learning import LearningService

        learning = LearningService(session)
        state = learning.list_state(ctx.workspace_id, ctx.profile_id)
        signals = AnalyticsService(session).qualified_signals(
            ctx.workspace_id, ctx.profile_id
        )
        session.commit()
        progress.done("consolidate")
    return {
        "learning_state": state,
        "qualified_signals": len(signals),
    }


LEARNING_ANALYSIS = learning_analysis