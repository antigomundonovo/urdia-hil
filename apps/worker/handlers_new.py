"""Stub job handlers for JobTypes whose milestone wiring has not landed.

Each stub receives the ExecutionContext, the payload dict and a JobProgress,
records a checkpoint step and returns a minimal result — enough for the
JobEngine to claim, run and audit the job. Production logic replaces these
as each Doc 17 milestone lands:

- DISCOVERY_SCAN / SOURCE_RETRIEVAL / CLAIM_VERIFICATION: apps.worker.handlers
- IMAGE_ANALYSIS / RIGHTS_RESEARCH / CLAIM_EXTRACTION / FORMAT_PLANNING /
  OPPORTUNITY_ANALYSIS: apps.worker.handlers_real
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


SOURCE_EXTRACTION = _noop_handler("source_extraction")
SOURCE_CLUSTERING = _noop_handler("source_clustering")
IMAGE_RESEARCH = _noop_handler("image_research")
ADVERSARIAL_RESEARCH = _noop_handler("adversarial_research")
CONTENT_GENERATION = _noop_handler("content_generation")
VISUAL_GENERATION = _noop_handler("visual_generation")
QC = _noop_handler("qc")
EXPORT = _noop_handler("export")
PUBLICATION = _noop_handler("publication")
ANALYTICS_SYNC = _noop_handler("analytics_sync")
COMMENT_SYNC = _noop_handler("comment_sync")
LEARNING_ANALYSIS = _noop_handler("learning_analysis")
