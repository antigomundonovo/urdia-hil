"""Content production, QC, human review, publisher gate, export
(Doc 17 steps 23-26; Docs 00 §21-22, 02, 03, 13, 16).

QC is deterministic (Doc 17 §10): every gate computed from the package's own
data; no "ignore gate" exists (Doc 06). The publisher gate (Doc 00 §22) only
accepts READY + APPROVED + RIGHTS_VERIFIED + PLATFORM_ALLOWED — a publication
record cannot even be created otherwise (fail closed).

Export (Doc 13): post-YYYY-MM-DD-ID folder with image/, captions/, sources/,
rights/, platform_variants/, manifest.json. Manifest records versions for
determinism.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.assets import Asset, RightsRecord
from packages.domain.editorial import (
    CanonicalContent,
    ContentPackage,
    Draft,
    Opportunity,
    OpportunityAsset,
    OpportunityClaim,
    PlatformVariant,
)
from packages.domain.enums import (
    ContentFormat,
    GateResult,
    OpportunityState,
    PublicationMethod,
    QualityGate,
    RightsClassification,
    RightsGateOutcome,
    UncertaintyState,
)
from packages.domain.knowledge import Claim, EvidenceRecord
from packages.domain.models import AuditEvent, Source
from packages.domain.repositories import AuditRepository
from packages.governance.audit import append_audit
from packages.providers.platform_catalog import get_declared, posting_method
from packages.research.opportunity import OpportunityService
from packages.research.rights import rights_gate
from packages.shared.execution_context import ExecutionContext
from packages.shared.settings import get_settings


class PublicationBlocked(Exception):
    """Fail closed: the publisher gate refused the package."""


class ContentService:
    MAX_EXPORT_IMAGE_BYTES = 25_000_000

    def __init__(
        self,
        session: Session,
        export_root: Path | None = None,
        asset_root: Path | None = None,
    ) -> None:
        self.session = session
        self.opps = OpportunityService(session)
        self.export_root = Path(export_root) if export_root else None
        self.asset_root = Path(asset_root or get_settings().asset_root).resolve()

    def _asset_file_path(self, asset: Asset) -> Path | None:
        if not asset.storage_path:
            return None
        relative_path = Path(asset.storage_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise PublicationBlocked("asset storage path is invalid")
        source_path = self.asset_root / relative_path
        if source_path.is_symlink():
            raise PublicationBlocked("asset storage path cannot be a symlink")
        try:
            resolved_source = source_path.resolve(strict=True)
            if not resolved_source.is_relative_to(self.asset_root):
                raise PublicationBlocked("asset storage path is outside asset storage")
            if not resolved_source.is_file():
                raise PublicationBlocked("asset file is unavailable")
            if resolved_source.stat().st_size > self.MAX_EXPORT_IMAGE_BYTES:
                raise PublicationBlocked("asset file exceeds export size limit")
            if not asset.file_hash:
                raise PublicationBlocked("asset file hash is missing")
            digest = hashlib.sha256()
            total_size = 0
            with resolved_source.open("rb") as image:
                for chunk in iter(lambda: image.read(1024 * 1024), b""):
                    total_size += len(chunk)
                    if total_size > self.MAX_EXPORT_IMAGE_BYTES:
                        raise PublicationBlocked("asset file exceeds export size limit")
                    digest.update(chunk)
            if digest.hexdigest() != asset.file_hash:
                raise PublicationBlocked("asset file integrity check failed")
        except OSError as exc:
            raise PublicationBlocked("asset file is unavailable") from exc
        return resolved_source

    def _attached_claim_ids(
        self, ctx: ExecutionContext, opp: Opportunity
    ) -> set[UUID]:
        return set(
            self.session.scalars(
                select(Claim.id)
                .join(OpportunityClaim, OpportunityClaim.ref_id == Claim.id)
                .where(
                    OpportunityClaim.opportunity_id == opp.id,
                    OpportunityClaim.workspace_id == ctx.workspace_id,
                    Claim.workspace_id == ctx.workspace_id,
                    Claim.profile_id == ctx.profile_id,
                )
            )
        )

    def _require_current_passing_qc(
        self, ctx: ExecutionContext, opp: Opportunity
    ) -> ContentPackage:
        package = self.session.scalars(
            select(ContentPackage)
            .where(ContentPackage.opportunity_id == opp.id)
            .order_by(ContentPackage.created_at.desc())
            .limit(1)
        ).first()
        if package is None:
            raise PublicationBlocked("content package has no passing QC")

        current_fingerprint = self._qc_input_fingerprint(ctx, package, opp)
        qc_events = self.session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.workspace_id == ctx.workspace_id,
                AuditEvent.action == "QC_RUN",
                AuditEvent.entity_type == "content_package",
                AuditEvent.entity_id == package.id,
            )
        )
        if not any(
            event.new_state in (GateResult.PASS.value, GateResult.WARNING.value)
            and (event.metadata_ or {}).get("input_fingerprint") == current_fingerprint
            for event in qc_events
        ):
            raise PublicationBlocked("content package requires a current passing QC")
        return package

    def _qc_input_fingerprint(
        self, ctx: ExecutionContext, package: ContentPackage, opp: Opportunity
    ) -> str:
        canonical = self.session.get(CanonicalContent, package.canonical_content_id)
        drafts = list(
            self.session.scalars(
                select(Draft).where(Draft.content_package_id == package.id)
            )
        )
        drafts.sort(key=lambda draft: str(draft.id))
        claim_ids = {
            str(claim_id)
            for draft in drafts
            for claim_id in (draft.claim_ids_used or [])
        }
        attached_claim_ids = self._attached_claim_ids(ctx, opp)
        claims = (
            list(
                self.session.scalars(
                    select(Claim).where(
                        Claim.id.in_(claim_ids),
                        Claim.workspace_id == ctx.workspace_id,
                        Claim.profile_id == ctx.profile_id,
                        Claim.id.in_(attached_claim_ids),
                    )
                )
            )
            if claim_ids and attached_claim_ids
            else []
        )
        claims.sort(key=lambda claim: str(claim.id))
        evidence = list(
            self.session.scalars(
                select(EvidenceRecord).where(
                    EvidenceRecord.claim_id.in_([claim.id for claim in claims]),
                    EvidenceRecord.workspace_id == ctx.workspace_id,
                    EvidenceRecord.profile_id == ctx.profile_id,
                )
            )
        ) if claims else []
        evidence.sort(key=lambda record: str(record.id))

        from packages.domain.editorial import PlatformPlan

        asset_ids = sorted(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(
                    OpportunityAsset.opportunity_id == opp.id,
                    OpportunityAsset.workspace_id == ctx.workspace_id,
                )
            ),
            key=str,
        )
        rights = []
        for asset_id in asset_ids:
            records = list(
                self.session.scalars(
                    select(RightsRecord).where(
                        RightsRecord.asset_id == asset_id,
                        RightsRecord.workspace_id == ctx.workspace_id,
                        RightsRecord.profile_id == ctx.profile_id,
                    )
                )
            )
            records.sort(key=lambda record: str(record.id))
            rights.extend(records)
        plans = list(
            self.session.scalars(
                select(PlatformPlan).where(
                    PlatformPlan.opportunity_id == opp.id,
                    PlatformPlan.workspace_id == ctx.workspace_id,
                )
            )
        )
        plans.sort(key=lambda plan: str(plan.id))

        fingerprint_data = {
            "qc_version": 1,
            "package": {"id": str(package.id), "format": package.format},
            "canonical": (
                {
                    "editorial_angle": canonical.editorial_angle,
                    "key_message": canonical.key_message,
                    "seo_entities": canonical.seo_entities,
                }
                if canonical
                else None
            ),
            "drafts": [
                {
                    "id": str(draft.id),
                    "title": draft.title,
                    "caption": draft.caption,
                    "payload": draft.payload,
                    "claim_ids_used": draft.claim_ids_used,
                }
                for draft in drafts
            ],
            "claims": [
                {"id": str(claim.id), "status": str(claim.status)}
                for claim in claims
            ],
            "evidence": [
                {
                    "id": str(record.id),
                    "claim_id": str(record.claim_id),
                    "supports": record.supports,
                    "excerpt": record.excerpt,
                    "source_id": str(record.source_id),
                }
                for record in evidence
            ],
            "assets": [str(asset_id) for asset_id in asset_ids],
            "asset_records": [
                {
                    "id": str(asset.id),
                    "file_hash": asset.file_hash,
                    "storage_path": asset.storage_path,
                    "status": asset.status,
                    "visual_classification": asset.visual_classification,
                }
                for asset in self.session.scalars(
                    select(Asset).where(
                        Asset.id.in_(asset_ids),
                        Asset.workspace_id == ctx.workspace_id,
                        Asset.profile_id == ctx.profile_id,
                    )
                )
            ],
            "rights": [
                {
                    "id": str(record.id),
                    "asset_id": str(record.asset_id),
                    "classification": record.classification,
                    "status": record.status,
                }
                for record in rights
            ],
            "platform_plans": [
                {"platform": plan.platform, "method": plan.method}
                for plan in plans
            ],
        }
        serialized = json.dumps(
            fingerprint_data, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    # --- canonical → package → draft ---------------------------------------

    def create_content(
        self,
        ctx: ExecutionContext,
        opp: Opportunity,
        *,
        format: ContentFormat,
        **canonical_fields,
    ) -> ContentPackage:
        canonical = CanonicalContent(
            workspace_id=ctx.workspace_id,
            opportunity_id=opp.id,
            **canonical_fields,
        )
        self.session.add(canonical)
        self.session.flush()
        package = ContentPackage(
            workspace_id=ctx.workspace_id,
            opportunity_id=opp.id,
            canonical_content_id=canonical.id,
            format=format.value,
        )
        self.session.add(package)
        self.session.flush()
        self.opps.advance_to(
            ctx, opp, OpportunityState.FORMAT_SELECTED, reason=f"format {format.value}"
        )
        return package

    def generate_draft(
        self,
        ctx: ExecutionContext,
        package: ContentPackage,
        *,
        title: str,
        caption: str,
        claim_ids_used: list | None = None,
        payload: dict | None = None,
    ) -> Draft:
        opp = self.session.get(Opportunity, package.opportunity_id)
        if opp is None or opp.state not in (
            OpportunityState.FORMAT_SELECTED.value,
            OpportunityState.PLATFORM_SELECTED.value,
            OpportunityState.DRAFTING.value,
        ):
            raise PublicationBlocked("content cannot be edited after QC has started")
        requested_claim_ids: set[UUID] = set()
        try:
            requested_claim_ids = {UUID(str(claim_id)) for claim_id in claim_ids_used or []}
        except (TypeError, ValueError) as exc:
            raise PublicationBlocked("draft references an invalid claim") from exc
        attached_claim_ids = self._attached_claim_ids(ctx, opp)
        if len(requested_claim_ids) != len(claim_ids_used or []):
            raise PublicationBlocked("draft claim references must be unique")
        if not requested_claim_ids.issubset(attached_claim_ids):
            raise PublicationBlocked("draft claims must belong to the opportunity")
        draft = Draft(
            workspace_id=ctx.workspace_id,
            content_package_id=package.id,
            title=title,
            caption=caption,
            payload=payload or {},
            claim_ids_used=sorted(str(claim_id) for claim_id in requested_claim_ids),
        )
        self.session.add(draft)
        self.session.flush()
        pre_draft = (
            OpportunityState.FORMAT_SELECTED.value,
            OpportunityState.PLATFORM_SELECTED.value,
        )
        if opp.state in pre_draft:
            self.opps.advance_to(
                ctx, opp, OpportunityState.DRAFTING, reason="draft generated"
            )
        append_audit(
            self.session,
            ctx=ctx,
            action="DRAFT_GENERATED",
            entity_type="content_package",
            entity_id=package.id,
            new_state="DRAFT",
        )
        return draft

    # --- QC (Doc 00 §21, Doc 02/03 gate lists) -------------------------------

    def run_qc(self, ctx: ExecutionContext, package: ContentPackage) -> dict:
        gates: dict[str, str] = {}
        blocking: list[str] = []
        warnings: list[str] = []
        opp = self.session.get(Opportunity, package.opportunity_id)
        canonical = self.session.get(CanonicalContent, package.canonical_content_id)
        draft = self.session.scalars(
            select(Draft)
            .where(Draft.content_package_id == package.id)
            .order_by(Draft.created_at.desc(), Draft.id.desc())
            .limit(1)
        ).first()

        def _set(gate: QualityGate, result: GateResult, note: str | None = None):
            gates[gate.value.lower().replace("-", "_")] = result.value
            if result is GateResult.FAIL and note:
                blocking.append(f"{gate.value}: {note}")
            if result is GateResult.WARNING and note:
                warnings.append(f"{gate.value}: {note}")

        # EVIDENCE + FACTUALITY + UNCERTAINTY — from the claims actually used
        claim_ids = list(draft.claim_ids_used or []) if draft else []
        attached_claim_ids = self._attached_claim_ids(ctx, opp)
        try:
            requested_claim_ids = {UUID(str(claim_id)) for claim_id in claim_ids}
        except (TypeError, ValueError):
            requested_claim_ids = set()
            _set(QualityGate.EVIDENCE, GateResult.FAIL, "draft references an invalid claim")
        invalid_claim_refs = len(requested_claim_ids) != len(claim_ids) or not (
            requested_claim_ids.issubset(attached_claim_ids)
        )
        claims = (
            list(
                self.session.scalars(
                    select(Claim).where(
                        Claim.id.in_(requested_claim_ids),
                        Claim.workspace_id == ctx.workspace_id,
                        Claim.profile_id == ctx.profile_id,
                    )
                )
            )
            if requested_claim_ids
            else []
        )
        if invalid_claim_refs:
            _set(
                QualityGate.EVIDENCE,
                GateResult.FAIL,
                "draft references a claim outside this opportunity",
            )
            _set(QualityGate.FACTUALITY, GateResult.FAIL)
            _set(QualityGate.UNCERTAINTY, GateResult.FAIL)
        elif not claim_ids:
            _set(QualityGate.EVIDENCE, GateResult.FAIL, "no claims referenced")
            _set(QualityGate.FACTUALITY, GateResult.FAIL)
            _set(QualityGate.UNCERTAINTY, GateResult.FAIL)
        else:
            missing = []
            controversial = []
            for claim in claims:
                records = list(
                    self.session.scalars(
                        select(EvidenceRecord).where(
                            EvidenceRecord.claim_id == claim.id,
                            EvidenceRecord.workspace_id == ctx.workspace_id,
                            EvidenceRecord.profile_id == ctx.profile_id,
                            EvidenceRecord.supports.is_(True),
                        )
                    )
                )
                status = claim.status.value if hasattr(claim.status, "value") else str(claim.status)
                if not records:
                    missing.append(str(claim.id))
                if status == UncertaintyState.CONTROVERSIAL.value:
                    controversial.append(str(claim.id))
            if missing:
                _set(
                    QualityGate.EVIDENCE,
                    GateResult.FAIL,
                    f"{len(missing)} claim(s) without supporting evidence",
                )
            else:
                _set(QualityGate.EVIDENCE, GateResult.PASS)
            missing.extend(
                str(claim_id)
                for claim_id in requested_claim_ids - {claim.id for claim in claims}
            )
            _set(QualityGate.FACTUALITY, GateResult.PASS if not missing else GateResult.FAIL)
            _set(
                QualityGate.UNCERTAINTY,
                GateResult.WARNING if controversial else GateResult.PASS,
                (
                    f"{len(controversial)} controversial claim(s): show uncertainty"
                    if controversial
                    else None
                ),
            )

        # RIGHTS — every asset of the opportunity through the gate
        asset_ids = list(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(
                    OpportunityAsset.opportunity_id == opp.id,
                    OpportunityAsset.workspace_id == ctx.workspace_id,
                )
            )
        )
        rights_ok = True
        visual_files_ok = True
        for aid in asset_ids:
            asset = self.session.scalar(
                select(Asset).where(
                    Asset.id == aid,
                    Asset.workspace_id == ctx.workspace_id,
                    Asset.profile_id == ctx.profile_id,
                    Asset.status == "ACTIVE",
                )
            )
            if asset is None:
                visual_files_ok = False
            else:
                try:
                    self._asset_file_path(asset)
                except PublicationBlocked:
                    visual_files_ok = False
            record = self.session.scalars(
                select(RightsRecord)
                .where(
                    RightsRecord.asset_id == aid,
                    RightsRecord.workspace_id == ctx.workspace_id,
                    RightsRecord.profile_id == ctx.profile_id,
                )
                .order_by(RightsRecord.created_at.desc(), RightsRecord.id.desc())
                .limit(1)
            ).first()
            if record is None or record.status != "VERIFIED" or rights_gate(
                RightsClassification(record.classification)
            ) is not RightsGateOutcome.MAY_PROCEED:
                rights_ok = False
        if asset_ids and rights_ok:
            _set(QualityGate.RIGHTS, GateResult.PASS)
        else:
            _set(
                QualityGate.RIGHTS,
                GateResult.FAIL,
                "asset without verified rights" if asset_ids else "no assets attached",
            )

        # VISUAL — assets exist
        _set(
            QualityGate.VISUAL,
            GateResult.PASS if asset_ids and visual_files_ok else GateResult.FAIL,
            "asset missing or local image failed integrity validation",
        )

        # ORIGINALITY — deterministic shingle check of the draft against the
        # evidence excerpts of the claims it uses (Doc 16: exact/near copy)
        source_texts: list[tuple[str, str]] = []
        if claim_ids:
            for record in self.session.scalars(
                select(EvidenceRecord).where(
                    EvidenceRecord.claim_id.in_(requested_claim_ids),
                    EvidenceRecord.workspace_id == ctx.workspace_id,
                    EvidenceRecord.profile_id == ctx.profile_id,
                )
            ):
                if record.excerpt:
                    source_texts.append((f"evidence:{record.id}", record.excerpt))
        if canonical and canonical.editorial_angle:
            source_texts.append(("canonical:angle", canonical.editorial_angle))
        if draft:
            from packages.research.analyzers import check_originality

            draft_text = f"{draft.title or ''} {draft.caption or ''}"
            originality = check_originality(draft_text, source_texts)
            _set(
                QualityGate.ORIGINALITY,
                GateResult(originality.result),
                "; ".join(originality.notes) or None,
            )
        else:
            _set(QualityGate.ORIGINALITY, GateResult.WARNING, "no draft to check")

        # SEO — canonical has entities
        seo_entities = (canonical.seo_entities or []) if canonical else []
        _set(
            QualityGate.SEO,
            GateResult.PASS if seo_entities else GateResult.WARNING,
            "no SEO entities",
        )

        # PLATFORM — platform plans exist for the opportunity
        from packages.domain.editorial import PlatformPlan

        platforms = list(
            self.session.scalars(
                select(PlatformPlan).where(PlatformPlan.opportunity_id == opp.id)
            )
        )
        _set(
            QualityGate.PLATFORM,
            GateResult.PASS if platforms else GateResult.WARNING,
            "no platform plans recorded",
        )

        # RELEVANCE — the Why must be stated (Doc 12)
        _set(
            QualityGate.RELEVANCE,
            GateResult.PASS if opp.why_profile else GateResult.WARNING,
            "why_profile empty",
        )
        # ANTI-SLOP — deterministic pt-BR heuristics; never FAILs (human judgement)
        from packages.research.analyzers import check_anti_slop

        slop = check_anti_slop(
            draft.title if draft else "", draft.caption if draft else ""
        )
        _set(
            QualityGate.ANTI_SLOP,
            GateResult(slop.result),
            "; ".join(slop.findings) or None,
        )

        # HUMAN_REVIEW — always REQUIRED in V1 (Doc 00 §22)
        gates["human_review"] = GateResult.REQUIRED.value

        if blocking:
            overall = GateResult.FAIL
        elif warnings:
            overall = GateResult.WARNING
        else:
            overall = GateResult.PASS
        result = {
            "status": overall.value,
            "gates": gates,
            "blocking_issues": blocking,
            "warnings": warnings,
        }
        append_audit(
            self.session,
            ctx=ctx,
            action="QC_RUN",
            entity_type="content_package",
            entity_id=package.id,
            new_state=overall.value,
            metadata={
                "gates": gates,
                "input_fingerprint": self._qc_input_fingerprint(ctx, package, opp),
            },
        )
        if opp.state == OpportunityState.DRAFTING.value and overall is not GateResult.FAIL:
            self.opps.advance_to(ctx, opp, OpportunityState.QUALITY_CONTROL, reason="QC")
        return result

    # --- human review (Doc 06 actions) ---------------------------------------

    def approve(self, ctx: ExecutionContext, opp: Opportunity, approved_by=None) -> Opportunity:
        """APPROVE: human authority (Doc 05/06). Moves QUALITY_CONTROL →
        HUMAN_REVIEW → READY. Approval is audited with the actor."""
        if opp.state != OpportunityState.QUALITY_CONTROL.value:
            raise PublicationBlocked("human approval requires completed QC")
        self._require_current_passing_qc(ctx, opp)
        current = OpportunityState(opp.state)
        if current is OpportunityState.QUALITY_CONTROL:
            self.opps.transition(
                ctx, opp, OpportunityState.HUMAN_REVIEW, reason="human review entered"
            )
        self.opps.transition(
            ctx, opp, OpportunityState.READY, reason="approved by human review"
        )
        append_audit(
            self.session,
            ctx=ctx,
            action="HUMAN_APPROVED",
            entity_type="opportunity",
            entity_id=opp.id,
            new_state=OpportunityState.READY.value,
            reason=f"approved_by={approved_by}" if approved_by else "approved",
        )
        return opp

    def reject(self, ctx: ExecutionContext, opp: Opportunity, reason: str) -> Opportunity:
        self.opps.transition(ctx, opp, OpportunityState.REJECTED, reason=reason)
        append_audit(
            self.session,
            ctx=ctx,
            action="HUMAN_REJECTED",
            entity_type="opportunity",
            entity_id=opp.id,
            new_state=OpportunityState.REJECTED.value,
            reason=reason,
        )
        return opp

    # --- publisher gate (Doc 00 §22) ------------------------------------------

    def publisher_gate(self, ctx: ExecutionContext, package: ContentPackage, platform: str) -> dict:
        """READY + APPROVED + RIGHTS_VERIFIED + PLATFORM_ALLOWED or nothing."""
        opp = self.session.get(Opportunity, package.opportunity_id)
        checks = {
            "READY": opp.state == OpportunityState.READY.value,
            "QC_PASSED": False,
        }
        try:
            latest_package = self._require_current_passing_qc(ctx, opp)
            checks["QC_PASSED"] = latest_package.id == package.id
        except PublicationBlocked:
            pass

        audit = AuditRepository(self.session).list_for_workspace(ctx.workspace_id, limit=500)
        checks["APPROVED"] = any(
            e.action == "HUMAN_APPROVED" and str(e.entity_id) == str(opp.id)
            for e in audit
        )

        # Revalidate asset ownership and local bytes at export time as well.
        asset_ids = list(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(
                    OpportunityAsset.opportunity_id == opp.id,
                    OpportunityAsset.workspace_id == ctx.workspace_id,
                )
            )
        )
        assets = list(
            self.session.scalars(
                select(Asset).where(
                    Asset.id.in_(asset_ids),
                    Asset.workspace_id == ctx.workspace_id,
                    Asset.profile_id == ctx.profile_id,
                    Asset.status == "ACTIVE",
                )
            )
        ) if asset_ids else []
        assets_by_id = {asset.id: asset for asset in assets}
        checks["ASSET_FILES_VALID"] = bool(asset_ids) and len(assets) == len(set(asset_ids))
        if checks["ASSET_FILES_VALID"]:
            for asset in assets:
                try:
                    self._asset_file_path(asset)
                except PublicationBlocked:
                    checks["ASSET_FILES_VALID"] = False
                    break

        # RIGHTS_VERIFIED for every asset
        def _asset_verified(aid) -> bool:
            record = self.session.scalars(
                select(RightsRecord)
                .where(
                    RightsRecord.asset_id == aid,
                    RightsRecord.workspace_id == ctx.workspace_id,
                    RightsRecord.profile_id == ctx.profile_id,
                )
                .order_by(RightsRecord.created_at.desc())
                .limit(1)
            ).first()
            if record is None or record.status != "VERIFIED":
                return False
            return (
                rights_gate(RightsClassification(record.classification))
                is RightsGateOutcome.MAY_PROCEED
            )

        checks["ASSET_FILES_VALID"] = checks["ASSET_FILES_VALID"] and all(
            aid in assets_by_id for aid in asset_ids
        )
        checks["RIGHTS_VERIFIED"] = bool(asset_ids) and all(
            _asset_verified(aid) for aid in asset_ids
        )

        # PLATFORM_ALLOWED — a platform plan exists for this platform
        from packages.domain.editorial import PlatformPlan

        plan = self.session.scalars(
            select(PlatformPlan).where(
                PlatformPlan.opportunity_id == opp.id, PlatformPlan.platform == platform
            )
        ).first()
        checks["PLATFORM_ALLOWED"] = plan is not None

        if not all(checks.values()):
            raise PublicationBlocked(
                f"publisher gate refused: {[k for k, v in checks.items() if not v]}"
            )
        return checks

    # --- manual posting kit (Doc 14: MANUAL platforms) --------------------------

    def _write_manual_posting_kit(
        self,
        *,
        export_dir: Path,
        platform: str,
        opportunity_title: str,
        draft: Draft,
        exported_assets: list[dict[str, Any]],
        used_claims: list[Claim],
        sources: list[Source],
        publication_id,
        approved_by,
    ) -> None:
        """For platforms without an official posting API (Doc 14 MANUAL,
        e.g. Kwai): generate a complete manual-posting kit — everything a
        human needs to post on the network, then confirm in URDIA."""
        declared = get_declared(platform)
        display_name = declared.display_name if declared else platform
        seo = (draft.payload or {}).get("seo") or {}
        keywords = ", ".join(str(k) for k in seo.get("keywords", []) if k)
        media_lines = [
            f"- `image/{entry['filename']}` ({entry.get('asset_type', 'PHOTO')})"
            for entry in exported_assets
            if entry.get("file_included") and entry.get("filename")
        ]
        media_lines.append("- `image/render-photo-post.png` (arte renderizada, se existir)")
        claims_block = "\n".join(
            f"- [{claim.status.value if hasattr(claim.status, 'value') else claim.status}] "
            f"{claim.normalized_text or claim.subject} (id {claim.id})"
            for claim in used_claims
        )
        sources_block = "\n".join(
            f"- {s.publisher or 'fonte'} — {s.url}" for s in sources
        )
        kit = f"""# Kit de Postagem Manual — {display_name}

Gerado pela URDIA em {datetime.now(UTC).isoformat(timespec="seconds")} —
pacote `{export_dir.name}`, aprovado por {approved_by or "humano"}.
Publicação-alvo: `{publication_id}`.

## Por que esta postagem é manual
{display_name} não oferece API oficial de publicação (verificado no
catálogo de capacidades, docs/PLATFORM_CAPABILITIES.md). Publique seguindo
os passos abaixo e depois confirme no sistema — a postagem só é marcada
como PUBLISHED após essa confirmação humana.

## Texto (copie e cole)
**Título:** {draft.title}

{draft.caption}
"""
        if keywords:
            hashtags = " ".join(
                f"#{str(k).replace(' ', '')}" for k in seo.get("keywords", []) if k
            )
            kit += f"\n**Hashtags sugeridas:** {hashtags}\n"
        kit += f"""
## Mídia (arquivos neste pacote)
{chr(10).join(media_lines) if media_lines else "- (sem mídia exportada)"}

## Passos sugeridos ({display_name})
1. Abra o {display_name} (app ou Creator Center) e faça login na conta do perfil.
2. Crie uma nova publicação e cole o texto acima.
3. Anexe a(s) mídia(s) indicadas na pasta `image/` deste pacote.
4. Revise a pré-visualização (enquadramento, legenda, hashtags).
5. Publique e copie o link/permalink da postagem.

## Rastreabilidade (não postar; uso interno)
### Claims usados
{claims_block or "- (nenhum)"}

### Fontes
{sources_block or "- (nenhuma)"}

## Depois de publicar
Confirme no sistema:
`POST /api/v1/publications/{publication_id}/confirm` com body
`{{"remote_url": "<link da postagem>"}}` — status PENDING → PUBLISHED.
"""
        kit_dir = export_dir / "platform_variants" / platform
        kit_dir.mkdir(parents=True, exist_ok=True)
        (kit_dir / "MANUAL_POSTING.md").write_text(kit, encoding="utf-8")

    # --- export (Doc 13) -------------------------------------------------------

    def export_package(self, ctx: ExecutionContext, package: ContentPackage, platform: str) -> Path:
        self.publisher_gate(ctx, package, platform)  # fails closed
        if self.export_root is None:
            raise PublicationBlocked("export root not configured")
        opp = self.session.get(Opportunity, package.opportunity_id)
        date_part = datetime.now(UTC).strftime("%Y-%m-%d")
        short_id = str(package.id)[:8]
        export_dir = self.export_root / f"post-{date_part}-{short_id}"
        for sub in (
            "image",
            "carousel",
            "microloop",
            "captions",
            "sources",
            "rights",
            "platform_variants",
        ):
            (export_dir / sub).mkdir(parents=True, exist_ok=True)
        (export_dir / "manifest.json").unlink(missing_ok=True)

        draft = self.session.scalars(
            select(Draft).where(Draft.content_package_id == package.id).limit(1)
        ).first()
        if draft:
            (export_dir / "captions" / "caption.txt").write_text(
                f"{draft.title or ''}\n\n{draft.caption or ''}", encoding="utf-8"
            )

        asset_ids = list(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(
                    OpportunityAsset.opportunity_id == opp.id,
                    OpportunityAsset.workspace_id == ctx.workspace_id,
                )
            )
        )
        assets = list(
            self.session.scalars(
                select(Asset).where(
                    Asset.id.in_(asset_ids),
                    Asset.workspace_id == ctx.workspace_id,
                    Asset.profile_id == ctx.profile_id,
                    Asset.status == "ACTIVE",
                )
            )
        ) if asset_ids else []
        if len(assets) != len(set(asset_ids)):
            raise PublicationBlocked("an opportunity asset is unavailable")
        exported_assets: list[dict[str, Any]] = []
        for asset in sorted(assets, key=lambda item: str(item.id)):
            filename = f"{asset.id}.bin"
            included = False
            if asset.storage_path:
                relative_path = Path(asset.storage_path)
                resolved_source = self._asset_file_path(asset)
                if resolved_source is None:
                    raise PublicationBlocked("asset file is unavailable")
                file_content = resolved_source.read_bytes()
                if len(file_content) > self.MAX_EXPORT_IMAGE_BYTES:
                    raise PublicationBlocked("asset file exceeds export size limit")
                if hashlib.sha256(file_content).hexdigest() != asset.file_hash:
                    raise PublicationBlocked("asset file integrity check failed")
                suffix = relative_path.suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
                    suffix = ".bin"
                filename = f"{asset.id}{suffix}"
                (export_dir / "image" / filename).write_bytes(file_content)
                included = True

            rights = self.session.scalars(
                select(RightsRecord)
                .where(
                    RightsRecord.asset_id == asset.id,
                    RightsRecord.workspace_id == ctx.workspace_id,
                    RightsRecord.profile_id == ctx.profile_id,
                )
                .order_by(RightsRecord.created_at.desc(), RightsRecord.id.desc())
                .limit(1)
            ).first()
            (export_dir / "image" / f"{asset.id}.json").write_text(
                json.dumps(
                    {
                        "asset_id": str(asset.id),
                        "asset_type": asset.asset_type,
                        "filename": filename if included else None,
                        "file_included": included,
                        "file_hash": asset.file_hash,
                        "original_file_url": asset.original_file_url,
                        "page_url": asset.page_url,
                        "institution": asset.institution,
                        "creator": asset.creator,
                        "creation_date": asset.creation_date,
                        "visual_classification": asset.visual_classification,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            exported_assets.append(
                {
                    "asset_id": str(asset.id),
                    "file_included": included,
                    "filename": filename if included else None,
                    "rights_record_id": str(rights.id) if rights else None,
                }
            )
            if rights:
                (export_dir / "rights" / f"{asset.id}.json").write_text(
                    json.dumps(
                        {
                            "asset_id": str(asset.id),
                            "classification": rights.classification,
                            "status": rights.status,
                            "license": rights.license,
                            "license_url": rights.license_url,
                            "rights_holder": rights.rights_holder,
                            "attribution_required": rights.attribution_required,
                            "attribution_text": rights.attribution_text,
                            "territory": rights.territory,
                            "commercial_use": rights.commercial_use,
                            "modification_allowed": rights.modification_allowed,
                            "evidence_source_id": (
                                str(rights.evidence_source_id)
                                if rights.evidence_source_id
                                else None
                            ),
                            "confidence": rights.confidence,
                            "verified_at": (
                                rights.verified_at.isoformat() if rights.verified_at else None
                            ),
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

        try:
            used_claim_ids = (
                {UUID(str(claim_id)) for claim_id in (draft.claim_ids_used or [])}
                if draft
                else set()
            )
        except (TypeError, ValueError) as exc:
            raise PublicationBlocked("draft claim references are invalid") from exc
        attached_claim_ids = self._attached_claim_ids(ctx, opp)
        used_claims = list(
            self.session.scalars(
                select(Claim).where(
                    Claim.id.in_(used_claim_ids),
                    Claim.workspace_id == ctx.workspace_id,
                    Claim.profile_id == ctx.profile_id,
                    Claim.id.in_(attached_claim_ids),
                )
            )
        ) if used_claim_ids else []
        evidence = list(
            self.session.scalars(
                select(EvidenceRecord).where(
                    EvidenceRecord.claim_id.in_([claim.id for claim in used_claims]),
                    EvidenceRecord.workspace_id == ctx.workspace_id,
                    EvidenceRecord.profile_id == ctx.profile_id,
                )
            )
        ) if used_claims else []
        source_ids = {
            record.source_id for record in evidence if record.source_id is not None
        }
        source_ids.update(
            asset_rights.evidence_source_id
            for asset_rights in self.session.scalars(
                select(RightsRecord).where(
                    RightsRecord.asset_id.in_(asset_ids),
                    RightsRecord.workspace_id == ctx.workspace_id,
                    RightsRecord.profile_id == ctx.profile_id,
                    RightsRecord.status == "VERIFIED",
                )
            )
            if asset_rights.evidence_source_id is not None
        )
        sources = list(
            self.session.scalars(
                select(Source).where(
                    Source.id.in_(source_ids),
                    Source.workspace_id == ctx.workspace_id,
                    Source.profile_id == ctx.profile_id,
                )
            )
        ) if source_ids else []
        for source in sources:
            (export_dir / "sources" / f"{source.id}.json").write_text(
                json.dumps(
                    {
                        "source_id": str(source.id),
                        "title": source.title,
                        "publisher": source.publisher,
                        "author": source.author,
                        "url": source.url,
                        "canonical_url": source.canonical_url,
                        "publication_date": (
                            source.publication_date.isoformat()
                            if source.publication_date
                            else None
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        (export_dir / "sources" / "claims-and-evidence.json").write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "claim_id": str(claim.id),
                            "text": (
                                claim.editorial_wording
                                or claim.normalized_text
                                or f"{claim.subject or ''} {claim.predicate or ''} "
                                f"{claim.object or ''}".strip()
                            ),
                            "status": (
                                claim.status.value
                                if hasattr(claim.status, "value")
                                else str(claim.status)
                            ),
                        }
                        for claim in used_claims
                    ],
                    "evidence": [
                        {
                            "evidence_id": str(record.id),
                            "claim_id": str(record.claim_id),
                            "source_id": str(record.source_id) if record.source_id else None,
                            "supports": record.supports,
                            "excerpt": record.excerpt,
                            "page_reference": record.page_reference,
                        }
                        for record in evidence
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        variant = PlatformVariant(
            workspace_id=ctx.workspace_id,
            content_package_id=package.id,
            platform=platform,
            payload={"exported_from": "V1 manual export"},
        )
        self.session.add(variant)
        render_block = self._render_outputs(
            ctx=ctx,
            package=package,
            draft=draft,
            used_claims=used_claims,
            sources=sources,
            exported_assets=exported_assets,
            export_dir=export_dir,
        )
        manifest = {
            "package_id": str(package.id),
            "opportunity_id": str(opp.id),
            "opportunity_title": opp.title,
            "format": package.format,
            "platform": platform,
            "exported_at": datetime.now(UTC).isoformat(),
            "export_version": 1,
            "rules": {"rights": "rights-1.0", "verification": "verification-1.0"},
            "human_approved": True,
            "assets": exported_assets,
            "source_count": len(sources),
            "claim_count": len(used_claims),
        }
        if render_block is not None:
            manifest["render"] = render_block
        (export_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # publication record (Doc 04): manual export is the V1 publication
        # method (Doc 14); idempotency key per Doc 14 — profile+content+platform
        from packages.domain.publishing import Publication

        existing = self.session.scalars(
            select(Publication).where(
                Publication.content_package_id == package.id,
                Publication.platform == platform,
            )
        ).first()
        if existing is None:
            publication = Publication(
                workspace_id=ctx.workspace_id,
                profile_id=opp.profile_id,
                content_package_id=package.id,
                platform=platform,
                method="EXPORT",
                status="PENDING",
                idempotency_key=f"{opp.profile_id}:{package.id}:{platform}:v1",
                approved_by=ctx.actor_id,
            )
            self.session.add(publication)
        self.session.flush()
        publication_record = existing or publication
        if posting_method(platform) is PublicationMethod.MANUAL:
            self._write_manual_posting_kit(
                export_dir=export_dir,
                platform=platform,
                opportunity_title=opp.title,
                draft=draft,
                exported_assets=exported_assets,
                used_claims=used_claims,
                sources=sources,
                publication_id=publication_record.id,
                approved_by=ctx.actor_id,
            )
        append_audit(
            self.session,
            ctx=ctx,
            action="PACKAGE_EXPORTED",
            entity_type="content_package",
            entity_id=package.id,
            new_state="EXPORTED",
            metadata={"platform": platform, "path": str(export_dir)},
        )
        return export_dir

    # --- rendering (Doc 13) ---------------------------------------------------

    def _render_outputs(
        self,
        *,
        ctx: ExecutionContext,
        package: ContentPackage,
        draft: Draft | None,
        used_claims: list[Claim],
        sources: list[Source],
        exported_assets: list[dict[str, Any]],
        export_dir: Path,
    ) -> dict[str, Any] | None:
        """Render stills for PHOTO_POST/CAROUSEL into the export folder and
        return the manifest "render" block (Doc 13 determinism + QC).
        MICROLOOP assembly is not part of V1 render — returns None unchanged.
        Fail closed: any render/QC error aborts the export."""
        from packages.rendering import engine as render_engine
        from packages.rendering import qc as render_qc

        first_asset_bytes: bytes | None = None
        requires_image = False
        for entry in exported_assets:
            if entry.get("file_included"):
                asset_file = export_dir / "image" / entry["filename"]
                first_asset_bytes = asset_file.read_bytes()
                requires_image = True
                break

        title = draft.title if draft else ""
        caption = draft.caption if draft else ""
        if package.format not in (ContentFormat.PHOTO_POST.value, ContentFormat.CAROUSEL.value):
            return None  # MICROLOOP: no still render in V1
        if not title and not caption:
            raise PublicationBlocked("draft has no text to render")

        try:
            rendered: list[tuple[str, render_engine.RenderedSlide, dict[str, str]]] = []
            if package.format == ContentFormat.PHOTO_POST.value:
                # Doc 13 ANM default: image-first, little text on the art —
                # only the hook goes on the image; the full caption ships in
                # captions/caption.txt.
                slide = render_engine.render_photo_post(
                    heading=title, body="", image_bytes=first_asset_bytes
                )
                (export_dir / "image" / "render-photo-post.png").write_bytes(slide.png)
                rendered.append(
                    (
                        "image/render-photo-post.png",
                        slide,
                        render_qc.validate_render(
                            slide,
                            expected_size=render_engine.DEFAULT_SIZE,
                            requires_image=requires_image,
                        ),
                    )
                )
            elif package.format == ContentFormat.CAROUSEL.value:
                canonical = self.session.get(CanonicalContent, package.canonical_content_id)
                claim_texts = [
                    claim.editorial_wording
                    or claim.normalized_text
                    or f"{claim.subject or ''} {claim.predicate or ''} {claim.object or ''}".strip()
                    for claim in used_claims
                ]
                source_labels = [
                    f"{s.publisher or s.title or 'Fonte registrada'}"
                    + (f" — {s.url}" if s.url else "")
                    for s in sources
                ]
                specs = render_engine.build_carousel_specs(
                    title=title,
                    caption=caption,
                    key_message=(canonical.key_message if canonical else "") or "",
                    editorial_angle=(canonical.editorial_angle if canonical else "") or "",
                    source_labels=source_labels,
                    first_image=first_asset_bytes,
                    claim_texts=claim_texts,
                )
                for index, (spec, role) in enumerate(
                    zip(specs, render_engine.CAROUSEL_SLIDES, strict=True), start=1
                ):
                    slide = render_engine.render_carousel_slide(spec)
                    slug = role.lower().replace(" / ", "-").replace(" ", "-")
                    path = f"carousel/slide-{index:02d}-{slug}.png"
                    (export_dir / path).write_bytes(slide.png)
                    rendered.append(
                        (
                            path,
                            slide,
                            render_qc.validate_render(
                                slide,
                                expected_size=render_engine.DEFAULT_SIZE,
                                requires_image=(index == 1 and requires_image),
                            ),
                        )
                    )
            else:
                return None  # MICROLOOP: no still render in V1

            block = render_engine.render_version_block()
            block.update(render_qc.render_metadata_block(rendered))
            if block["summary"] != "PASS":
                raise PublicationBlocked(
                    f"render QC failed: {[k for k, v in block['qc'].items() if v == 'FAIL']}"
                )
            return block
        except PublicationBlocked:
            raise
        except Exception as exc:
            raise PublicationBlocked(f"render failed: {exc}") from exc
