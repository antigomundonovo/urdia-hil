"""Evidence + deterministic verification (Doc 17 step 18; Doc 16 must-pass).

Verification rules (declared, deterministic, no LLM in the loop — Doc 17 §10):

- 0 evidence                          → UNKNOWN (and claim is NOT pipeline-ready;
                                        Doc 16: claim without evidence → NOT_READY)
- any contradicting evidence          → CONTROVERSIAL + Contradiction row preserving
                                        both sides (Doc 16: independent contradictory
                                        sources → CONTROVERSIAL, preserve both sides)
- ≥2 supporting INDEPENDENT groups    → PROBABLE (corroboration; a copy is never
                                        independence — Doc 00 §28)
- exactly 1 supporting group          → POSSIBLE
- CONFIRMED / REFUTED are never awarded by this engine: they require human
  review or the adversarial-research milestone (conservative reading of
  "afirme pouco").
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.enums import UncertaintyState
from packages.domain.knowledge import Claim, Contradiction, EvidenceRecord, Verdict
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext

RULE_VERSION = "verification-1.0"


@dataclass
class VerificationOutcome:
    verdict: UncertaintyState
    supporting_groups: int
    contradicting_sources: int
    reason: str


def _independence_key(evidence: EvidenceRecord) -> str:
    """Copies from the same source (or same declared group) are ONE group."""
    return evidence.independence_group or f"source:{evidence.source_id}"


class KnowledgeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- reads (scoped) ---------------------------------------------------

    def get_claim_scoped(self, claim_id, workspace_id) -> Claim | None:
        claim = self.session.get(Claim, claim_id)
        if claim is None or claim.workspace_id != workspace_id:
            return None
        return claim

    def evidence_for(self, claim_id) -> list[EvidenceRecord]:
        return list(
            self.session.scalars(
                select(EvidenceRecord).where(EvidenceRecord.claim_id == claim_id)
            )
        )

    # --- write paths ------------------------------------------------------

    def add_claim(
        self,
        ctx: ExecutionContext,
        *,
        story_id=None,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        normalized_text: str | None = None,
        claim_type: str | None = None,
        temporal_scope: str | None = None,
        geographic_scope: str | None = None,
        importance: int | None = None,
        interpretation_flag: bool | None = None,
    ) -> Claim:
        if ctx.profile_id is None:
            raise ValueError("claim requires a profile context")
        claim = Claim(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            story_id=story_id,
            subject=subject,
            predicate=predicate,
            object=object,
            normalized_text=normalized_text,
            claim_type=claim_type,
            temporal_scope=temporal_scope,
            geographic_scope=geographic_scope,
            importance=importance,
            status=UncertaintyState.UNKNOWN,  # nothing is confirmed on creation
            interpretation_flag=interpretation_flag,
        )
        self.session.add(claim)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="CLAIM_CREATED",
            entity_type="claim",
            entity_id=claim.id,
            new_state=claim.status.value,
        )
        return claim

    def add_evidence(
        self,
        ctx: ExecutionContext,
        *,
        claim_id,
        supports: bool,
        source_id=None,
        evidence_type: str | None = None,
        excerpt: str | None = None,
        url: str | None = None,
        page_reference: str | None = None,
        snapshot_reference: str | None = None,
        independence_group: str | None = None,
        strength: int | None = None,
    ) -> EvidenceRecord:
        claim = self.get_claim_scoped(claim_id, ctx.workspace_id)
        if claim is None:
            raise LookupError("claim not found in workspace")
        record = EvidenceRecord(
            workspace_id=ctx.workspace_id,
            profile_id=claim.profile_id,
            claim_id=claim.id,
            source_id=source_id,
            evidence_type=evidence_type,
            excerpt=excerpt,
            page_reference=page_reference,
            url=url,
            snapshot_reference=snapshot_reference,
            supports=supports,
            strength=strength,
            independence_group=independence_group,
            retrieved_at=datetime.now(UTC),
        )
        self.session.add(record)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="EVIDENCE_ADDED",
            entity_type="claim",
            entity_id=claim.id,
            new_state="SUPPORTS" if supports else "CONTRADICTS",
            evidence_ids=[str(record.id)],
        )
        self.verify_claim(ctx, claim)
        return record

    # --- deterministic verification ---------------------------------------

    def verify_claim(self, ctx: ExecutionContext, claim: Claim) -> VerificationOutcome:
        records = self.evidence_for(claim.id)
        supporting = [e for e in records if e.supports]
        contradicting = [e for e in records if not e.supports]
        support_groups = len({_independence_key(e) for e in supporting})
        contra_sources = len({_independence_key(e) for e in contradicting})

        if contradicting:
            verdict = UncertaintyState.CONTROVERSIAL
            reason = (
                f"{contra_sources} contradicting source(s) preserved against "
                f"{len(supporting)} supporting record(s)"
            )
            self._record_contradiction(ctx, claim, supporting, contradicting)
        elif support_groups >= 2:
            verdict = UncertaintyState.PROBABLE
            reason = f"corroborated by {support_groups} independent group(s)"
        elif support_groups == 1:
            verdict = UncertaintyState.POSSIBLE
            reason = "single independent supporting source"
        else:
            verdict = UncertaintyState.UNKNOWN
            reason = (
                "no evidence recorded" if not records else "supporting records lack independence"
            )

        # verdict history: append, never rewrite (Doc 15)
        self.session.add(
            Verdict(
                workspace_id=claim.workspace_id,
                profile_id=claim.profile_id,
                claim_id=claim.id,
                verdict=verdict,
                reason=reason,
                rule_version=RULE_VERSION,
                supporting_groups=support_groups,
                contradicting_sources=contra_sources,
            )
        )

        previous = claim.status
        previous_value = previous.value if hasattr(previous, "value") else str(previous)
        claim.status = verdict
        claim.last_reviewed_at = datetime.now(UTC)
        self.session.flush()

        append_audit(
            self.session,
            ctx=ctx,
            action="CLAIM_VERIFIED",
            entity_type="claim",
            entity_id=claim.id,
            previous_state=previous_value,
            new_state=verdict.value,
            reason=reason,
            rule_version=RULE_VERSION,
        )
        return VerificationOutcome(verdict, support_groups, contra_sources, reason)

    def _record_contradiction(
        self,
        ctx: ExecutionContext,
        claim: Claim,
        supporting: list[EvidenceRecord],
        contradicting: list[EvidenceRecord],
    ) -> None:
        existing = self.session.scalars(
            select(Contradiction).where(
                Contradiction.claim_id == claim.id, Contradiction.status == "OPEN"
            )
        ).first()
        supporting_side = [
            {"evidence_id": str(e.id), "source_id": str(e.source_id) if e.source_id else None}
            for e in supporting
        ]
        contradicting_side = [
            {"evidence_id": str(e.id), "source_id": str(e.source_id) if e.source_id else None}
            for e in contradicting
        ]
        if existing is not None:
            existing.supporting_side = supporting_side
            existing.contradicting_side = contradicting_side
        else:
            self.session.add(
                Contradiction(
                    workspace_id=claim.workspace_id,
                    profile_id=claim.profile_id,
                    claim_id=claim.id,
                    description="independent contradictory sources",
                    supporting_side=supporting_side,
                    contradicting_side=contradicting_side,
                )
            )
        self.session.flush()

    # --- pipeline gate (Doc 16) --------------------------------------------

    def claims_pipeline_ready(self, claim_ids: list) -> bool:
        """Doc 16: claim without evidence → NOT_READY. A claim is ready only
        with at least one supporting evidence record."""
        if not claim_ids:
            return False
        records = list(
            self.session.scalars(
                select(EvidenceRecord).where(
                    EvidenceRecord.claim_id.in_(claim_ids),
                    EvidenceRecord.supports.is_(True),
                )
            )
        )
        covered = {r.claim_id for r in records}
        return all(cid in covered for cid in claim_ids)
