"""Rights + provenance (Doc 17 step 20; Doc 11).

Absolute rule (Doc 00 §15): UNKNOWN = NÃO PUBLICAR. Negative assumption
(Doc 11): not finding a restriction does NOT mean public domain — an asset
without a verified rights record is UNKNOWN and blocks.

Gate (Doc 11): UNKNOWN/PROHIBITED/PERMISSION_REQUIRED → BLOCK;
only VERIFIED MAY_PROCEED. Any future override requires elevated permission
+ reason + actor + audit — overrides are NOT implemented in V1.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.assets import Asset, RightsRecord
from packages.domain.enums import RightsClassification, RightsGateOutcome, rights_gate
from packages.domain.models import Source
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext

RULE_VERSION = "rights-1.0"


class RightsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- classification ---------------------------------------------------

    def classify(
        self,
        ctx: ExecutionContext,
        *,
        asset_id,
        classification: RightsClassification,
        license: str | None = None,
        license_url: str | None = None,
        rights_holder: str | None = None,
        attribution_required: bool | None = None,
        attribution_text: str | None = None,
        territory: str | None = None,
        commercial_use: bool | None = None,
        modification_allowed: bool | None = None,
        evidence_source_id=None,
        confidence: int | None = None,
        notes: str | None = None,
    ) -> RightsRecord:
        """Registers a rights classification for an asset. The record's
        `status` starts as the classification itself; only explicit
        verification (verify()) can mark it VERIFIED."""
        asset = self._asset_scoped(ctx, asset_id)
        if evidence_source_id is not None:
            source = self.session.scalars(
                select(Source).where(
                    Source.id == evidence_source_id,
                    Source.workspace_id == asset.workspace_id,
                    Source.profile_id == asset.profile_id,
                )
            ).first()
            if source is None:
                raise LookupError("evidence source not found in profile")
        record = RightsRecord(
            workspace_id=asset.workspace_id,
            profile_id=asset.profile_id,
            asset_id=asset.id,
            classification=classification.value,
            license=license,
            license_url=license_url,
            rights_holder=rights_holder,
            attribution_required=attribution_required,
            attribution_text=attribution_text,
            territory=territory,
            commercial_use=commercial_use,
            modification_allowed=modification_allowed,
            evidence_source_id=evidence_source_id,
            confidence=confidence,
            status=classification.value,
            notes=notes,
        )
        self.session.add(record)
        self.session.flush()

        asset.rights_confidence = confidence
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="RIGHTS_CLASSIFIED",
            entity_type="asset",
            entity_id=asset.id,
            new_state=classification.value,
            reason=notes,
            rule_version=RULE_VERSION,
        )
        return record

    def verify(
        self,
        ctx: ExecutionContext,
        record: RightsRecord,
        verified_by=None,
    ) -> RightsRecord:
        """Explicit verification step (Doc 11 workflow: classification →
        verification → publishable/blocked)."""
        scoped_record = self.session.scalars(
            select(RightsRecord).where(
                RightsRecord.id == record.id,
                RightsRecord.workspace_id == ctx.workspace_id,
                RightsRecord.profile_id == ctx.profile_id,
            )
        ).first()
        if scoped_record is None:
            raise LookupError("rights record not found in profile")
        self._asset_scoped(ctx, scoped_record.asset_id)
        record = scoped_record
        record.status = "VERIFIED"
        record.verified_at = datetime.now(UTC)
        record.verified_by = verified_by
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="RIGHTS_VERIFIED",
            entity_type="asset",
            entity_id=record.asset_id,
            new_state="VERIFIED",
            rule_version=RULE_VERSION,
        )
        return record

    # --- the gate ---------------------------------------------------------

    def evaluate(self, ctx: ExecutionContext, asset_id) -> RightsGateOutcome:
        """Doc 11 gate, fail closed: only a VERIFIED record whose
        classification is not blocking may proceed. An asset with NO rights
        record at all is UNKNOWN → BLOCK (negative assumption)."""
        asset = self._asset_scoped(ctx, asset_id)
        record = self.session.scalars(
            select(RightsRecord)
            .where(
                RightsRecord.asset_id == asset.id,
                RightsRecord.workspace_id == ctx.workspace_id,
                RightsRecord.profile_id == ctx.profile_id,
            )
            .order_by(RightsRecord.created_at.desc())
            .limit(1)
        ).first()
        if record is None:
            return RightsGateOutcome.BLOCK  # no record = UNKNOWN
        if record.status != "VERIFIED":
            return RightsGateOutcome.BLOCK
        return rights_gate(RightsClassification(record.classification))

    def latest_record(self, ctx: ExecutionContext, asset_id) -> RightsRecord | None:
        asset = self._asset_scoped(ctx, asset_id)
        return self.session.scalars(
            select(RightsRecord)
            .where(
                RightsRecord.asset_id == asset.id,
                RightsRecord.workspace_id == ctx.workspace_id,
                RightsRecord.profile_id == ctx.profile_id,
            )
            .order_by(RightsRecord.created_at.desc())
            .limit(1)
        ).first()

    # --- helpers -----------------------------------------------------------

    def _asset_scoped(self, ctx: ExecutionContext, asset_id) -> Asset:
        asset = self.session.get(Asset, asset_id)
        if (
            asset is None
            or asset.workspace_id != ctx.workspace_id
            or asset.profile_id != ctx.profile_id
        ):
            raise LookupError("asset not found in profile")
        return asset
