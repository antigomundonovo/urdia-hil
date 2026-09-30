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

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.assets import RightsRecord
from packages.domain.editorial import (
    CanonicalContent,
    ContentPackage,
    Draft,
    Opportunity,
    PlatformVariant,
)
from packages.domain.enums import (
    ContentFormat,
    GateResult,
    OpportunityState,
    QualityGate,
    RightsClassification,
    RightsGateOutcome,
    UncertaintyState,
)
from packages.domain.knowledge import Claim, EvidenceRecord
from packages.domain.models import AuditEvent
from packages.domain.repositories import AuditRepository
from packages.governance.audit import append_audit
from packages.research.opportunity import OpportunityService
from packages.research.rights import rights_gate
from packages.shared.execution_context import ExecutionContext


class PublicationBlocked(Exception):
    """Fail closed: the publisher gate refused the package."""


class ContentService:
    def __init__(self, session: Session, export_root: Path | None = None) -> None:
        self.session = session
        self.opps = OpportunityService(session)
        self.export_root = Path(export_root) if export_root else None

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

        current_fingerprint = self._qc_input_fingerprint(package, opp)
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

    def _qc_input_fingerprint(self, package: ContentPackage, opp: Opportunity) -> str:
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
        claims = list(
            self.session.scalars(select(Claim).where(Claim.id.in_(claim_ids)))
        ) if claim_ids else []
        claims.sort(key=lambda claim: str(claim.id))
        evidence = list(
            self.session.scalars(
                select(EvidenceRecord).where(
                    EvidenceRecord.claim_id.in_([claim.id for claim in claims])
                )
            )
        ) if claims else []
        evidence.sort(key=lambda record: str(record.id))

        from packages.domain.editorial import OpportunityAsset, PlatformPlan

        asset_ids = sorted(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(
                    OpportunityAsset.opportunity_id == opp.id
                )
            ),
            key=str,
        )
        rights = []
        for asset_id in asset_ids:
            records = list(
                self.session.scalars(
                    select(RightsRecord).where(RightsRecord.asset_id == asset_id)
                )
            )
            records.sort(key=lambda record: str(record.id))
            rights.extend(records)
        plans = list(
            self.session.scalars(
                select(PlatformPlan).where(PlatformPlan.opportunity_id == opp.id)
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
        draft = Draft(
            workspace_id=ctx.workspace_id,
            content_package_id=package.id,
            title=title,
            caption=caption,
            payload=payload or {},
            claim_ids_used=claim_ids_used or [],
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
        claims = (
            list(self.session.scalars(select(Claim).where(Claim.id.in_(claim_ids))))
            if claim_ids
            else []
        )
        if not claim_ids:
            _set(QualityGate.EVIDENCE, GateResult.FAIL, "no claims referenced")
        else:
            missing = []
            controversial = []
            for claim in claims:
                records = list(
                    self.session.scalars(
                        select(EvidenceRecord).where(
                            EvidenceRecord.claim_id == claim.id,
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
        from packages.domain.editorial import OpportunityAsset

        asset_ids = list(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(OpportunityAsset.opportunity_id == opp.id)
            )
        )
        rights_ok = True
        for aid in asset_ids:
            record = self.session.scalars(
                select(RightsRecord)
                .where(RightsRecord.asset_id == aid)
                .order_by(RightsRecord.created_at.desc())
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
            GateResult.PASS if asset_ids else GateResult.FAIL,
            "no assets attached",
        )

        # ORIGINALITY — deterministic shingle check of the draft against the
        # evidence excerpts of the claims it uses (Doc 16: exact/near copy)
        source_texts: list[tuple[str, str]] = []
        if claim_ids:
            for record in self.session.scalars(
                select(EvidenceRecord).where(EvidenceRecord.claim_id.in_(claim_ids))
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
                "input_fingerprint": self._qc_input_fingerprint(package, opp),
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

        # RIGHTS_VERIFIED for every asset
        from packages.domain.editorial import OpportunityAsset

        asset_ids = list(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(OpportunityAsset.opportunity_id == opp.id)
            )
        )
        def _asset_verified(aid) -> bool:
            record = self.session.scalars(
                select(RightsRecord)
                .where(RightsRecord.asset_id == aid)
                .order_by(RightsRecord.created_at.desc())
                .limit(1)
            ).first()
            if record is None or record.status != "VERIFIED":
                return False
            return (
                rights_gate(RightsClassification(record.classification))
                is RightsGateOutcome.MAY_PROCEED
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

    # --- export (Doc 13) -------------------------------------------------------

    def export_package(self, ctx: ExecutionContext, package: ContentPackage, platform: str) -> Path:
        self.publisher_gate(ctx, package, platform)  # fails closed
        if self.export_root is None:
            raise PublicationBlocked("export root not configured")
        opp = self.session.get(Opportunity, package.opportunity_id)
        date_part = datetime.now(UTC).strftime("%Y-%m-%d")
        short_id = str(package.id)[:8]
        export_dir = self.export_root / f"post-{date_part}-{short_id}"
        for sub in ("image", "captions", "sources", "rights", "platform_variants"):
            (export_dir / sub).mkdir(parents=True, exist_ok=True)

        draft = self.session.scalars(
            select(Draft).where(Draft.content_package_id == package.id).limit(1)
        ).first()
        if draft:
            (export_dir / "captions" / "caption.txt").write_text(
                f"{draft.title or ''}\n\n{draft.caption or ''}", encoding="utf-8"
            )

        variant = PlatformVariant(
            workspace_id=ctx.workspace_id,
            content_package_id=package.id,
            platform=platform,
            payload={"exported_from": "V1 manual export"},
        )
        self.session.add(variant)
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
        }
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
