"""Opportunity + JEV (Doc 17 steps 21-22; Doc 12).

The Opportunity is the central unit (Doc 00 §10). Its state moves only
through the TransitionService (Doc 03 checklist, audited).

JEV here is the deterministic layer of the recommendation engine (Doc 12
decisions): it never invents urgency, and it FAILS CLOSED on evidence and
rights — claims without supporting evidence force NEEDS_RESEARCH, blocking
rights force the gate downstream. requires_human_review is always True in
V1 (Doc 00 §22).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.editorial import (
    Opportunity,
    OpportunityAsset,
    OpportunityClaim,
    OpportunitySource,
)
from packages.domain.enums import (
    JEVDecision,
    OpportunityState,
    RightsGateOutcome,
    UncertaintyState,
)
from packages.domain.knowledge import Claim
from packages.governance.audit import append_audit
from packages.governance.transition_service import TransitionService
from packages.research.rights import RightsService
from packages.shared.execution_context import ExecutionContext


class JEVRecommendationResult:
    def __init__(self, decision: JEVDecision, priority: str, reasons: list[str]):
        self.decision = decision
        self.priority = priority
        self.reasons = reasons
        self.requires_human_review = True  # Doc 00 §22: V1 always


class OpportunityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.transitions = TransitionService(session)
        self.rights = RightsService(session)

    # --- lifecycle ---------------------------------------------------------

    def create(
        self,
        ctx: ExecutionContext,
        *,
        title: str,
        story_id=None,
        description: str | None = None,
        why_now: str | None = None,
        why_profile: str | None = None,
    ) -> Opportunity:
        if ctx.profile_id is None:
            raise ValueError("opportunity requires profile context")
        # Doc 12: never invent urgency — what arrives is what is kept
        opp = Opportunity(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            story_id=story_id,
            title=title,
            description=description,
            why_now=why_now,
            why_profile=why_profile,
            # enters the machine at CANDIDATE
            state=OpportunityState.CANDIDATE.value,
        )
        self.session.add(opp)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="OPPORTUNITY_CREATED",
            entity_type="opportunity",
            entity_id=opp.id,
            new_state=opp.state,
        )
        return opp

    def get_scoped(self, opportunity_id, workspace_id) -> Opportunity | None:
        opp = self.session.get(Opportunity, opportunity_id)
        if opp is None or opp.workspace_id != workspace_id:
            return None
        return opp

    def list_for_profile(self, workspace_id, profile_id, state: str | None = None):
        stmt = select(Opportunity).where(
            Opportunity.workspace_id == workspace_id,
            Opportunity.profile_id == profile_id,
        )
        if state:
            stmt = stmt.where(Opportunity.state == state)
        return list(self.session.scalars(stmt.order_by(Opportunity.created_at.desc())))

    def attach(
        self,
        ctx: ExecutionContext,
        opportunity: Opportunity,
        *,
        source_ids=(),
        claim_ids=(),
        asset_ids=(),
    ):
        for sid in source_ids:
            self.session.add(
                OpportunitySource(
                    workspace_id=ctx.workspace_id, opportunity_id=opportunity.id, ref_id=sid
                )
            )
        for cid in claim_ids:
            self.session.add(
                OpportunityClaim(
                    workspace_id=ctx.workspace_id, opportunity_id=opportunity.id, ref_id=cid
                )
            )
        for aid in asset_ids:
            self.session.add(
                OpportunityAsset(
                    workspace_id=ctx.workspace_id, opportunity_id=opportunity.id, ref_id=aid
                )
            )
        self.session.flush()
        return opportunity

    def transition(
        self,
        ctx: ExecutionContext,
        opp: Opportunity,
        target: OpportunityState,
        *,
        reason: str | None = None,
        **kwargs,
    ):
        """Move the opportunity through the state machine (audited, fail closed)."""
        current = OpportunityState(opp.state)
        self.transitions.apply(
            ctx,
            entity_type="opportunity",
            entity_id=opp.id,
            current=current,
            target=target,
            reason=reason,
            **kwargs,
        )
        opp.state = target.value
        self.session.flush()
        return opp

    # --- JEV (deterministic layer) ------------------------------------------

    def jev_recommend(self, ctx: ExecutionContext, opp: Opportunity) -> JEVRecommendationResult:
        """Deterministic recommendation from the opportunity's own data
        (Doc 12). Human review always required in V1."""
        reasons: list[str] = []

        claims = list(
            self.session.scalars(
                select(Claim)
                .join(OpportunityClaim, OpportunityClaim.ref_id == Claim.id)
                .where(OpportunityClaim.opportunity_id == opp.id)
            )
        )

        # evidence gate (Doc 16): every claim needs >=1 supporting record;
        # status may be enum (fresh) or str (loaded) — normalize before compare
        def _val(status):
            return status.value if hasattr(status, "value") else str(status)

        missing_evidence = [
            str(c.id) for c in claims if _val(c.status) == UncertaintyState.UNKNOWN.value
        ]
        if claims and missing_evidence:
            return JEVRecommendationResult(
                JEVDecision.NEEDS_RESEARCH,
                "LOW",
                reasons
                + [f"{len(missing_evidence)} claim(s) without evidence — research first"],
            )

        controversial = [
            c for c in claims if _val(c.status) == UncertaintyState.CONTROVERSIAL.value
        ]
        if controversial:
            reasons.append(
                f"{len(controversial)} controversial claim(s) — decide whether to show both sides"
            )

        # rights gate (Doc 11/16): EVERY attached asset is evaluated — an
        # asset without any rights record is UNKNOWN and blocks (fail closed)
        assets = list(
            self.session.scalars(
                select(OpportunityAsset.ref_id).where(
                    OpportunityAsset.opportunity_id == opp.id
                )
            )
        )
        blocking_assets = []
        for aid in assets:
            if self.rights.evaluate(ctx, aid) is not RightsGateOutcome.MAY_PROCEED:
                blocking_assets.append(str(aid))
        if blocking_assets:
            reasons.append(f"{len(blocking_assets)} asset(s) fail the rights gate")
            return JEVRecommendationResult(
                JEVDecision.QUARANTINE,
                "LOW",
                reasons + ["rights must resolve first"],
            )

        if not claims:
            reasons.append("no claims attached — cannot affirm anything yet")
            return JEVRecommendationResult(JEVDecision.NEEDS_RESEARCH, "LOW", reasons)

        decision = JEVDecision.PROCEED
        priority = "MEDIUM"
        if controversial:
            priority = "HIGH"  # conflict needs a human decision, not volume
            reasons.append("CONTROVERSIAL: preserve both sides (Doc 16)")
        reasons.append("all claims carry supporting evidence; rights gate clear")
        return JEVRecommendationResult(decision, priority, reasons)

    def jev_decide(
        self,
        ctx: ExecutionContext,
        opp: Opportunity,
        decision: JEVDecision,
        reason: str | None = None,
    ) -> Opportunity:
        """Records the (human-reviewed) JEV decision and applies its state
        transition. PROCEED advances the machine; other decisions park it."""
        rec = self.jev_recommend(ctx, opp)
        opp.decision = decision.value
        opp.decision_reason = reason or "; ".join(rec.reasons)
        opp.priority = rec.priority

        state_map = {
            JEVDecision.PROCEED: OpportunityState.RESEARCHING,
            JEVDecision.NEEDS_RESEARCH: OpportunityState.NEEDS_RESEARCH,
            JEVDecision.QUARANTINE: OpportunityState.QUARANTINED,
            JEVDecision.REJECT: OpportunityState.REJECTED,
        }
        # (SERIES_CANDIDATE / EXPERIMENT_CANDIDATE park in place: their state
        # transitions are editorial decisions, not pipeline moves)
        target = state_map.get(decision)
        if target is not None:
            self.transition(ctx, opp, target, reason=opp.decision_reason)
        append_audit(
            self.session,
            ctx=ctx,
            action="JEV_DECIDED",
            entity_type="opportunity",
            entity_id=opp.id,
            new_state=opp.state,
            reason=opp.decision_reason,
        )
        return opp
