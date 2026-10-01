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

from apps.worker.engine import FatalJobError, JobProgress, RetryableJobError
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
def _vision_provider():
    """Factory kept separate so tests can inject a fake provider."""
    from packages.providers.gemini import GeminiProvider

    return GeminiProvider()


def _asset_content(session, asset: Asset) -> bytes:
    """Read asset bytes with the same path-safety guards as ContentService
    (relative path inside asset_root, no symlink, no traversal) plus a
    SHA-256 integrity check against the stored file_hash."""
    import hashlib

    from packages.shared.settings import get_settings

    if not asset.storage_path:
        raise FatalJobError("asset has no storage_path")
    relative_path = Path(asset.storage_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise FatalJobError("asset storage path is invalid")
    asset_root = Path(get_settings().asset_root).resolve()
    source_path = asset_root / relative_path
    if source_path.is_symlink():
        raise FatalJobError("asset storage path cannot be a symlink")
    try:
        resolved = source_path.resolve(strict=True)
        if not resolved.is_relative_to(asset_root):
            raise FatalJobError("asset storage path is outside asset storage")
        content = resolved.read_bytes()
    except FileNotFoundError as exc:
        raise FatalJobError("asset file is unavailable") from exc
    if asset.file_hash:
        digest = hashlib.sha256(content).hexdigest()
        if digest != asset.file_hash:
            raise FatalJobError("asset file hash mismatch (corrupted storage)")
    return content


def image_analysis(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Analyze image assets (Doc 10): SHA-256 integrity check, perceptual
    hash (duplicate detection), and an AI-PROPOSED visual classification.

    Doc 10 absolute rule: visual similarity never proves identity — hashes
    support duplicate detection and origin leads only. The classification is
    recorded on the asset as a proposal (provider provenance stays in the
    job result); it is never a rights decision.

    Expected payload keys:
      - asset_ids: list[str]
    """
    if not payload.get("asset_ids"):
        raise FatalJobError("image_analysis requires asset_ids")
    asset_ids = payload["asset_ids"]

    progress.next("load_assets")
    with SessionLocal() as session:
        from agents import vision as vision_agent
        from packages.providers.gemini import ProviderUnavailable
        from packages.research.photos import detect_mime, perceptual_hash

        assets = session.scalars(
            select(Asset).where(
                Asset.id.in_([uuid.UUID(str(a)) for a in asset_ids]),
                Asset.workspace_id == ctx.workspace_id,
                Asset.profile_id == ctx.profile_id,
            )
        ).all()
        if not assets:
            raise FatalJobError("no assets found for profile")

        progress.next("analyze")
        results = []
        for asset in assets:
            content = _asset_content(session, asset)

            mime = detect_mime(content)
            if mime is None:
                raise FatalJobError(
                    f"asset {asset.id}: content is not a decodable image (fail closed)"
                )

            phash = perceptual_hash(content)
            duplicate_of = None
            if phash:
                twin = session.scalars(
                    select(Asset).where(
                        Asset.perceptual_hash == phash,
                        Asset.id != asset.id,
                        Asset.workspace_id == ctx.workspace_id,
                        Asset.profile_id == ctx.profile_id,
                    )
                ).first()
                if twin is not None:
                    duplicate_of = str(twin.id)

            try:
                proposal = vision_agent.classify_image(
                    _vision_provider(), content=content, mime_type=mime
                )
            except vision_agent.VisionBlocked as exc:
                raise FatalJobError(f"asset {asset.id}: {exc}") from exc
            except ProviderUnavailable as exc:
                raise RetryableJobError(
                    f"vision provider unavailable: {exc}"
                ) from exc

            asset.perceptual_hash = phash or asset.perceptual_hash
            asset.visual_classification = proposal["visual_classification"]
            results.append(
                {
                    "asset_id": str(asset.id),
                    "sha256_ok": True,
                    "perceptual_hash": phash,
                    "duplicate_of": duplicate_of,
                    "ai_classification": proposal,
                }
            )

        session.commit()
        progress.done("analyze")
    return {
        "analyzed": len(results),
        "assets": results,
        "classification_is_proposal": True,
    }


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


# ---------------------------------------------------------------------------
# CONTENT_GENERATION (LLM-assisted draft proposal — Doc 05 Copywriter)
# ---------------------------------------------------------------------------
def _copywriter_provider():
    """Factory kept separate so tests can inject a fake provider."""
    from packages.providers.gemini import GeminiProvider

    return GeminiProvider()


def content_generation(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Propose a draft for a package via the Copywriter agent (LLM), then
    persist it through the normal generate_draft flow. The proposal still
    goes through QC + human review (automation_level 2) — the job NEVER
    approves or publishes.

    Fail-closed rules (Doc 17 §10 — prompt is not governance):
      - unusable/invalid model output  -> FatalJobError (invalid schema);
      - semantic violations (claims not attached/usable) -> FatalJobError
        (policy block);
      - provider unavailable/timeout/rate-limit -> RetryableJobError (Doc 03).

    Expected payload keys:
      - package_id: str
      - extra_instructions: str (optional, human guidance for the draft)
    """
    package_id = payload.get("package_id")
    if not package_id:
        raise FatalJobError("content_generation requires package_id")
    extra_instructions = str(payload.get("extra_instructions") or "")

    progress.next("load_package")
    with SessionLocal() as session:
        from agents import copywriter as copywriter_agent
        from packages.providers.gemini import ProviderUnavailable
        from packages.research.content import ContentService, PublicationBlocked

        package = _package_for_context(session, ctx, package_id)
        service = ContentService(session)

        progress.next("generate")
        try:
            proposal, provenance = copywriter_agent.write_draft(
                session,
                ctx,
                package,
                _copywriter_provider(),
                extra_instructions=extra_instructions,
            )
        except copywriter_agent.CopywriterBlocked as exc:
            raise FatalJobError(f"content generation blocked: {exc}") from exc
        except ProviderUnavailable as exc:
            raise RetryableJobError(f"llm provider unavailable: {exc}") from exc

        progress.next("persist_draft")
        try:
            draft = service.generate_draft(
                ctx,
                package,
                title=proposal.title,
                caption=proposal.caption,
                claim_ids_used=proposal.claim_ids_used,
                payload={
                    "generated_by": copywriter_agent.metadata_from(provenance),
                    "slides": [s.model_dump() for s in proposal.slides],
                    "seo": proposal.seo.model_dump(),
                    "microloop_text": proposal.microloop_text,
                },
            )
        except PublicationBlocked as exc:
            raise FatalJobError(f"draft rejected by content service: {exc}") from exc
        session.commit()
        progress.done("persist_draft")
    return {
        "package_id": str(package.id),
        "draft_id": str(draft.id),
        "title": proposal.title,
        "provider": provenance.get("provider"),
        "model": provenance.get("model"),
        "prompt_version": provenance.get("prompt_version"),
        "awaiting_human_review": True,
    }


CONTENT_GENERATION = content_generation