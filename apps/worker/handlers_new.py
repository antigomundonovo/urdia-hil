"""Stub job handlers for JobTypes whose milestone wiring has not landed.

Each stub receives the ExecutionContext, the payload dict and a JobProgress,
records a checkpoint step and returns a minimal result — enough for the
JobEngine to claim, run and audit the job. Production logic replaces these
as each Doc 17 milestone lands:

- DISCOVERY_SCAN / SOURCE_RETRIEVAL / CLAIM_VERIFICATION: apps.worker.handlers
- IMAGE_ANALYSIS / RIGHTS_RESEARCH / CLAIM_EXTRACTION / FORMAT_PLANNING /
  OPPORTUNITY_ANALYSIS / QC / EXPORT / ANALYTICS_SYNC / COMMENT_SYNC /
  LEARNING_ANALYSIS: apps.worker.handlers_real

The 6 remaining stubs below are intentionally NOT implemented in V1
(Doc 17 Core Rule: no invented features):
- SOURCE_EXTRACTION / SOURCE_CLUSTERING: covered by the discovery scan;
  a separate pipeline would duplicate it without a spec.
- IMAGE_RESEARCH / ADVERSARIAL_RESEARCH: require external search APIs
  (human batch: search provider registration + benchmark, Doc 17 §15).
- VISUAL_GENERATION: Doc 13 render runs inside export_package; a standalone
  job would duplicate it without a spec.
- PUBLICATION: automated publishing violates Amendment 007 / Doc 14 —
  publication is manual-confirm in V1.
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
VISUAL_GENERATION = _noop_handler("visual_generation")
PUBLICATION = _noop_handler("publication")
