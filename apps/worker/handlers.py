"""Job handlers (Doc 17 step 13 wiring). Registered into the JobEngine;
each handler opens its own session so the worker loop stays transaction-safe.

DISCOVERY_SCAN payload:
  {"workspace_id": "...", "profile_id": "...", "source_id": "..." (optional —
   single-source scan for POST /sources/{id}/retrieve)}
"""

import uuid
from typing import Any

from apps.worker.engine import JobProgress
from packages.research.discovery import DiscoveryEngine
from packages.research.fetcher import SafeFetcher
from packages.shared.db import SessionLocal
from packages.shared.execution_context import ExecutionContext


def discovery_scan(ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress) -> dict:
    from packages.domain.models import Source

    progress.done("resolve_sources")
    progress.next("fetch")
    workspace_id = uuid.UUID(str(payload["workspace_id"]))
    profile_id = uuid.UUID(str(payload["profile_id"])) if payload.get("profile_id") else None
    source_id = uuid.UUID(str(payload["source_id"])) if payload.get("source_id") else None

    with SessionLocal() as session:
        fetcher = SafeFetcher()
        engine = DiscoveryEngine(session, fetcher)
        if source_id is not None:
            source = session.get(Source, source_id)
            if source is None or source.workspace_id != workspace_id:
                raise ValueError("source not found in workspace")
            sources = [source]
        elif profile_id is not None:
            sources = engine.active_sources(workspace_id, profile_id)
        else:
            raise ValueError("payload requires source_id or profile_id")

        progress.done("fetch")
        progress.next("normalize_and_cluster")
        reports = [engine.scan_source(source) for source in sources]
        session.commit()

    progress.done("normalize_and_cluster")
    return {
        "scanned": len(reports),
        "items_new": sum(r.items_new for r in reports),
        "duplicates": sum(r.duplicates for r in reports),
        "failed": [str(r.source_id) for r in reports if r.status == "FAILED"],
    }


def claim_verification(
    ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress
) -> dict:
    """Recompute deterministic verdicts (Doc 16) for a story's claims — or all
    profile claims when no story_id is given."""
    from sqlalchemy import select

    from packages.domain.knowledge import Claim
    from packages.research.verification import KnowledgeService

    progress.done("resolve_claims")
    progress.next("verify")
    workspace_id = uuid.UUID(str(payload["workspace_id"]))
    profile_id = uuid.UUID(str(payload["profile_id"])) if payload.get("profile_id") else None
    story_id = uuid.UUID(str(payload["story_id"])) if payload.get("story_id") else None

    with SessionLocal() as session:
        service = KnowledgeService(session)
        stmt = select(Claim).where(Claim.workspace_id == workspace_id)
        if story_id is not None:
            stmt = stmt.where(Claim.story_id == story_id)
        elif profile_id is not None:
            stmt = stmt.where(Claim.profile_id == profile_id)
        claims = list(session.scalars(stmt))
        outcomes = {
            str(claim.id): service.verify_claim(ctx, claim).verdict.value for claim in claims
        }
        session.commit()

    progress.done("verify")
    return {"verified": len(outcomes), "verdicts": outcomes}
