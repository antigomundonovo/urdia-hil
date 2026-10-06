"""Social intelligence service (AMENDMENT-2026-10-02-013).

FactualityChallenge pipeline (contract §11):

  Comentário → FactualityChallenge → Research Reach → Evidence →
  Judge determinístico → confirmed/disputed/unsupported/unknown →
  Human review

ABSOLUTE RULE (contract §11): a comment is never evidence by itself.
The comment only SUPPLIES the statement; evidence enters exclusively
through the registered research path (Doc 09) with provenance, and the
verdict comes from the single deterministic judge (Doc 16) — there is
no second Judge/System 2 (contract §4).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.knowledge import Claim
from packages.domain.models import Profile, WorkspaceMember
from packages.domain.publishing import Comment
from packages.domain.social import FactualityChallenge, SocialInboxItem
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext

# Judge mapping (contract §11) from the deterministic engine's verdicts
# (Doc 16). CONFIRMED here means "supported by evidence" — the formal
# human review (review_challenge) remains the authoritative gate.
JUDGE_MAPPING = {
    "CONTROVERSIAL": "DISPUTED",
    "REFUTED": "DISPUTED",
    "PROBABLE": "CONFIRMED",
    "POSSIBLE": "CONFIRMED",
    "UNKNOWN": "UNSUPPORTED",
}

CHALLENGE_STATUSES = ("PROPOSED", "RESOLVED", "DISMISSED")
CHALLENGE_VERDICTS = ("CONFIRMED", "DISPUTED", "UNSUPPORTED", "UNKNOWN")


INBOX_STATUSES = ("UNREAD", "OPEN", "RESOLVED", "IGNORED")

class SocialError(Exception):
    """Fail closed on social intelligence rule violations."""


class SocialIntelligenceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _require_profile(self, ctx: ExecutionContext) -> Profile:
        if ctx.profile_id is None:
            raise SocialError("profile context required")
        profile = self.session.get(Profile, ctx.profile_id)
        if profile is None or profile.workspace_id != ctx.workspace_id:
            raise SocialError("profile not found in workspace")
        return profile

    def _require_workspace_member(self, workspace_id, user_id) -> None:
        if user_id is None:
            raise SocialError("human reviewer required")
        member = self.session.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if member is None:
            raise SocialError("user is not a workspace member")

    # --- challenges ---------------------------------------------------------

    def create_challenge(
        self,
        ctx: ExecutionContext,
        *,
        comment_id,
        statement: str,
    ) -> FactualityChallenge:
        """Turn a comment's factual claim into a researchable challenge.
        The comment is the SOURCE of the question, never the evidence."""
        from packages.research.verification import KnowledgeService

        self._require_profile(ctx)
        if not statement or not statement.strip():
            raise SocialError("challenge requires a non-empty statement")

        comment = self.session.get(Comment, comment_id)
        if (
            comment is None
            or comment.workspace_id != ctx.workspace_id
            or comment.profile_id != ctx.profile_id
        ):
            raise SocialError("comment not found in profile")

        knowledge = KnowledgeService(self.session)
        claim = knowledge.add_claim(
            ctx,
            normalized_text=statement.strip(),
            claim_type="factuality_challenge",
        )
        challenge = FactualityChallenge(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            comment_id=comment.id,
            statement=statement.strip(),
            claim_id=claim.id,
            status="PROPOSED",
        )
        self.session.add(challenge)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_CHALLENGE_CREATED",
            entity_type="factuality_challenge",
            entity_id=challenge.id,
            new_state="PROPOSED",
            metadata={"comment_id": str(comment.id), "claim_id": str(claim.id)},
        )
        return challenge

    def research_challenge(
        self,
        ctx: ExecutionContext,
        challenge_id,
    ) -> FactualityChallenge:
        """Run the deterministic judge over the challenge's claim. Evidence
        itself is gathered through the normal research paths (add_evidence);
        this step only maps the judge's verdict onto the challenge."""
        from packages.research.verification import KnowledgeService

        challenge = self.get_challenge(ctx, challenge_id)
        if challenge is None:
            raise SocialError("challenge not found in profile")
        if challenge.status != "PROPOSED":
            raise SocialError(f"challenge is not PROPOSED (current: {challenge.status})")
        if challenge.claim_id is None:
            raise SocialError("challenge has no linked claim")

        claim = self.session.get(Claim, challenge.claim_id)
        if (
            claim is None
            or claim.workspace_id != ctx.workspace_id
            or claim.profile_id != ctx.profile_id
        ):
            raise SocialError("claim not found in profile")
        outcome = KnowledgeService(self.session).verify_claim(ctx, claim)
        challenge.verdict = JUDGE_MAPPING.get(outcome.verdict.value, "UNKNOWN")
        challenge.verdict_reason = outcome.reason
        challenge.verdict_metadata = {
            "engine_verdict": outcome.verdict.value,
            "supporting_groups": outcome.supporting_groups,
            "contradicting_sources": outcome.contradicting_sources,
            "judge": "deterministic-verification-1.0",
            "note": "CONFIRMED here means supported by evidence; formal "
            "confirmation is the human review gate",
        }
        challenge.status = "RESOLVED"
        challenge.researched_at = datetime.now(UTC)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_CHALLENGE_RESEARCHED",
            entity_type="factuality_challenge",
            entity_id=challenge.id,
            new_state="RESOLVED",
            metadata={
                "engine_verdict": outcome.verdict.value,
                "challenge_verdict": challenge.verdict,
            },
        )
        return challenge

    def review_challenge(
        self,
        ctx: ExecutionContext,
        challenge_id,
        *,
        verdict: str,
        reason: str | None = None,
        reviewed_by=None,
    ) -> FactualityChallenge:
        """HUMAN GATE (contract §11): the human review confirms or adjusts
        the verdict. This is the authoritative resolution of a challenge."""
        if verdict not in CHALLENGE_VERDICTS:
            raise SocialError(f"invalid verdict: {verdict}")
        self._require_profile(ctx)
        challenge = self.get_challenge(ctx, challenge_id)
        if challenge is None:
            raise SocialError("challenge not found in profile")
        if challenge.status == "DISMISSED":
            raise SocialError("dismissed challenges cannot be reviewed")
        self._require_workspace_member(ctx.workspace_id, reviewed_by)
        challenge.verdict = verdict
        if reason:
            challenge.verdict_reason = reason
        challenge.status = "RESOLVED"
        challenge.reviewed_by = reviewed_by
        challenge.reviewed_at = datetime.now(UTC)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_CHALLENGE_REVIEWED",
            entity_type="factuality_challenge",
            entity_id=challenge.id,
            new_state=verdict,
            reason=reason,
        )
        return challenge

    def dismiss_challenge(
        self, ctx: ExecutionContext, challenge_id, *, reason: str
    ) -> FactualityChallenge:
        challenge = self.get_challenge(ctx, challenge_id)
        if challenge is None:
            raise SocialError("challenge not found in profile")
        if challenge.status not in ("PROPOSED", "RESOLVED"):
            raise SocialError(f"challenge cannot be dismissed (current: {challenge.status})")
        challenge.status = "DISMISSED"
        challenge.verdict_reason = reason
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_CHALLENGE_DISMISSED",
            entity_type="factuality_challenge",
            entity_id=challenge.id,
            new_state="DISMISSED",
            reason=reason,
        )
        return challenge

    def get_challenge(self, ctx: ExecutionContext, challenge_id) -> FactualityChallenge | None:
        self._require_profile(ctx)
        return self.session.scalars(
            select(FactualityChallenge).where(
                FactualityChallenge.id == challenge_id,
                FactualityChallenge.workspace_id == ctx.workspace_id,
                FactualityChallenge.profile_id == ctx.profile_id,
            )
        ).first()

    def list_challenges(
        self, ctx: ExecutionContext, status: str | None = None
    ) -> list[FactualityChallenge]:
        self._require_profile(ctx)
        stmt = select(FactualityChallenge).where(
            FactualityChallenge.workspace_id == ctx.workspace_id,
            FactualityChallenge.profile_id == ctx.profile_id,
        )
        if status:
            stmt = stmt.where(FactualityChallenge.status == status)
        return list(
            self.session.scalars(stmt.order_by(FactualityChallenge.created_at.desc()))
        )

    # --- social inbox --------------------------------------------------------

    def create_inbox_item(
        self,
        ctx: ExecutionContext,
        *,
        item_type: str = "COMMENT",
        comment_id: uuid.UUID | None = None,
    ) -> "SocialInboxItem":

        self._require_profile(ctx)
        if item_type not in ("COMMENT", "MENTION", "DM"):
            raise SocialError(f"invalid inbox item type: {item_type}")
        if comment_id is not None:
            comment = self.session.get(Comment, comment_id)
            if (
                comment is None
                or comment.workspace_id != ctx.workspace_id
                or comment.profile_id != ctx.profile_id
            ):
                raise SocialError("comment not found in profile")

        item = SocialInboxItem(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            comment_id=comment_id,
            item_type=item_type,
            status="UNREAD",
        )
        self.session.add(item)
        self.session.flush()
        
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_INBOX_ITEM_CREATED",
            entity_type="social_inbox_item",
            entity_id=item.id,
            new_state="UNREAD",
        )
        return item

    def update_inbox_item_status(
        self,
        ctx: ExecutionContext,
        item_id: uuid.UUID,
        status: str,
    ) -> "SocialInboxItem":
        item = self.get_inbox_item(ctx, item_id)
        if item is None:
            raise SocialError("inbox item not found")
        if status not in ("UNREAD", "OPEN", "RESOLVED", "IGNORED"):
            raise SocialError(f"invalid status: {status}")

        item.status = status
        self.session.flush()

        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_INBOX_ITEM_UPDATED",
            entity_type="social_inbox_item",
            entity_id=item.id,
            new_state=status,
        )
        return item
        
    def assign_inbox_item(
        self,
        ctx: ExecutionContext,
        item_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> "SocialInboxItem":
        item = self.get_inbox_item(ctx, item_id)
        if item is None:
            raise SocialError("inbox item not found")
        if user_id is not None:
            self._require_workspace_member(ctx.workspace_id, user_id)

        item.assigned_to = user_id
        if item.status == "UNREAD":
            item.status = "OPEN"

        self.session.flush()

        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_INBOX_ITEM_ASSIGNED",
            entity_type="social_inbox_item",
            entity_id=item.id,
            metadata={"assigned_to": str(user_id) if user_id else None},
        )
        return item

    def get_inbox_item(self, ctx: ExecutionContext, item_id: uuid.UUID):
        self._require_profile(ctx)
        return self.session.scalars(
            select(SocialInboxItem).where(
                SocialInboxItem.id == item_id,
                SocialInboxItem.workspace_id == ctx.workspace_id,
                SocialInboxItem.profile_id == ctx.profile_id,
            )
        ).first()

    def list_inbox_items(self, ctx: ExecutionContext, status: str | None = None):
        self._require_profile(ctx)
        stmt = select(SocialInboxItem).where(
            SocialInboxItem.workspace_id == ctx.workspace_id,
            SocialInboxItem.profile_id == ctx.profile_id,
        )
        if status:
            stmt = stmt.where(SocialInboxItem.status == status)
        return list(
            self.session.scalars(stmt.order_by(SocialInboxItem.created_at.desc()))
        )


    # --- audience pulse & demand bridge ---------------------------------------

    def compute_pulse(self, ctx: ExecutionContext, period_start, period_end):
        self._require_profile(ctx)
        from packages.domain.publishing import Comment
        from packages.domain.social import AudiencePulse

        stmt = select(Comment).where(
            Comment.workspace_id == ctx.workspace_id,
            Comment.profile_id == ctx.profile_id,
            Comment.created_at >= period_start,
            Comment.created_at <= period_end,
        )
        comments = list(self.session.scalars(stmt))
        total = len(comments)

        sentiment_sum = 0.0
        clusters = {}
        for c in comments:
            if c.qualified_signal:
                intent_upper = (c.intent or "").upper()
                sentiment_sum += 0.1 if "POSITIVE" in intent_upper else (
                    -0.1 if "NEGATIVE" in intent_upper else 0.0
                )
                key = c.qualified_signal
                if key in clusters:
                    clusters[key]["count"] += 1
                else:
                    clusters[key] = {"count": 1, "sample": c.text[:100] if c.text else ""}

        score = sentiment_sum / total if total > 0 else 0.0
        pulse = AudiencePulse(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            period_start=period_start,
            period_end=period_end,
            sentiment_score=round(score, 4),
            topic_clusters=clusters,
        )
        self.session.add(pulse)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_PULSE_COMPUTED",
            entity_type="audience_pulse",
            entity_id=pulse.id,
            new_state="GENERATED",
            metadata={"comment_count": total},
        )
        return pulse

    def detect_demand(
        self,
        ctx: ExecutionContext,
        *,
        summary: str,
        unique_people_count: int,
        platforms: list[str],
        evidence: dict | None = None,
    ):
        from packages.domain.social import AudienceDemand

        self._require_profile(ctx)
        demand = AudienceDemand(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            summary=summary,
            evidence=evidence or {},
            unique_people_count=unique_people_count,
            growth=0.0,
            engagement=0.0,
            platforms=platforms,
            confidence=0.0,
            editorial_fit=0.0,
        )
        self.session.add(demand)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_DEMAND_DETECTED",
            entity_type="audience_demand",
            entity_id=demand.id,
            new_state="DETECTED",
        )
        return demand

    def export_demand_for_studio(self, ctx: ExecutionContext, demand_id: uuid.UUID):
        demand = self.get_demand(ctx, demand_id)
        if demand is None:
            raise SocialError("demand not found")
        return {
            "id": str(demand.id),
            "summary": demand.summary,
            "evidence": demand.evidence,
            "unique_people_count": demand.unique_people_count,
            "growth": demand.growth,
            "engagement": demand.engagement,
            "platforms": demand.platforms,
            "confidence": demand.confidence,
            "editorial_fit": demand.editorial_fit,
            "created_at": demand.created_at.isoformat(),
        }

    def decide_demand(
        self,
        ctx: ExecutionContext,
        demand_id: uuid.UUID,
        *,
        decision: str,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ):
        """Owner's human decision on a demand (contrato §10). Append-only
        audit; the bridge exposes the decision read-only to the Studio."""
        from datetime import datetime as _dt

        if decision not in {"APPROVED", "REJECTED"}:
            raise SocialError("decision must be APPROVED or REJECTED")
        demand = self.get_demand(ctx, demand_id)
        if demand is None:
            raise SocialError("demand not found")
        previous = demand.decision
        demand.decision = decision
        demand.decided_at = _dt.now(UTC)
        demand.decided_by = actor_id
        append_audit(
            self.session,
            ctx=ctx,
            action="SOCIAL_DEMAND_DECIDED",
            entity_type="audience_demand",
            entity_id=demand.id,
            previous_state=previous,
            new_state=decision,
            reason=reason,
        )
        self.session.flush()
        return demand

    def get_demand(self, ctx: ExecutionContext, demand_id: uuid.UUID):
        from packages.domain.social import AudienceDemand
        self._require_profile(ctx)
        return self.session.scalars(
            select(AudienceDemand).where(
                AudienceDemand.id == demand_id,
                AudienceDemand.workspace_id == ctx.workspace_id,
                AudienceDemand.profile_id == ctx.profile_id,
            )
        ).first()

    def list_audience_demand(self, ctx: ExecutionContext):
        from packages.domain.social import AudienceDemand
        self._require_profile(ctx)
        stmt = select(AudienceDemand).where(
            AudienceDemand.workspace_id == ctx.workspace_id,
            AudienceDemand.profile_id == ctx.profile_id,
        )
        return list(self.session.scalars(stmt.order_by(AudienceDemand.created_at.desc())))

    def get_latest_audience_pulse(self, ctx: ExecutionContext):
        from packages.domain.social import AudiencePulse
        self._require_profile(ctx)
        return self.session.scalars(
            select(AudiencePulse).where(
                AudiencePulse.workspace_id == ctx.workspace_id,
                AudiencePulse.profile_id == ctx.profile_id,
            ).order_by(AudiencePulse.created_at.desc()).limit(1)
        ).first()

    def list_demands(self, ctx: ExecutionContext):
        from packages.domain.social import AudienceDemand
        self._require_profile(ctx)
        stmt = select(AudienceDemand).where(
            AudienceDemand.workspace_id == ctx.workspace_id,
            AudienceDemand.profile_id == ctx.profile_id,
        )
        return list(self.session.scalars(stmt.order_by(AudienceDemand.created_at.desc())))

    def get_pulse(self, ctx: ExecutionContext, pulse_id: uuid.UUID):
        from packages.domain.social import AudiencePulse
        self._require_profile(ctx)
        return self.session.scalars(
            select(AudiencePulse).where(
                AudiencePulse.id == pulse_id,
                AudiencePulse.workspace_id == ctx.workspace_id,
                AudiencePulse.profile_id == ctx.profile_id,
            )
        ).first()

    def list_pulses(self, ctx: ExecutionContext):
        from packages.domain.social import AudiencePulse
        self._require_profile(ctx)
        stmt = select(AudiencePulse).where(
            AudiencePulse.workspace_id == ctx.workspace_id,
            AudiencePulse.profile_id == ctx.profile_id,
        )
        return list(self.session.scalars(stmt.order_by(AudiencePulse.created_at.desc())))
