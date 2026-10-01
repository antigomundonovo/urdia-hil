"""Extra Job handlers (stub implementations) for remaining JobTypes.

Each handler receives a ``ExecutionContext``, the payload dict, and a ``JobProgress``.

The stubs do not perform real work – they simply record a checkpoint and return
a minimal result. They allow the JobEngine to claim and run every job type.

The real handlers should be implemented later with the actual business logic.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.worker.engine import JobProgress
from packages.shared.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


def _noop_handler(name: str):
    def handler(ctx: ExecutionContext, payload: dict[str, Any], progress: JobProgress) -> dict:
        logger.debug("Handler %s: started", name)
        progress.done(name)
        return {"handler": name, "status": "ok"}
    return handler

# Stub implementations for the 19 remaining JobTypes
OPPORTUNITY_ANALYSIS = _noop_handler("opportunity_analysis")
SOURCE_EXTRACTION = _noop_handler("source_extraction")
SOURCE_CLUSTERING = _noop_handler("source_clustering")
IMAGE_ANALYSIS = _noop_handler("image_analysis")
IMAGE_RESEARCH = _noop_handler("image_research")
RIGHTS_RESEARCH = _noop_handler("rights_research")
CLAIM_EXTRACTION = _noop_handler("claim_extraction")
ADVERSARIAL_RESEARCH = _noop_handler("adversarial_research")
FORMAT_PLANNING = _noop_handler("format_planning")
CONTENT_GENERATION = _noop_handler("content_generation")
VISUAL_GENERATION = _noop_handler("visual_generation")
QC = _noop_handler("qc")
EXPORT = _noop_handler("export")
PUBLICATION = _noop_handler("publication")
ANALYTICS_SYNC = _noop_handler("analytics_sync")
COMMENT_SYNC = _noop_handler("comment_sync")
LEARNING_ANALYSIS = _noop_handler("learning_analysis")
SOURCE_RETRIEVAL = _noop_handler("source_retrieval")
DISCOVERY_SCAN = _noop_handler("discovery_scan")
CLAIM_VERIFICATION = _noop_handler("claim_verification")
""