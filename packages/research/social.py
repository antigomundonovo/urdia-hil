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

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.knowledge import Claim
from packages.domain.publishing import Comment
from packages.domain.social import FactualityChallenge
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


class SocialError(Exception):
    """Fail closed on social intelligence rule violations."""


class SocialIntelligenceService:
    def __init__(self, session: Session) -> None:
        self.session = session

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

        if ctx.profile_id is None:
            raise SocialError("factuality challenge requires a profile context")
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
        challenge = self.get_challenge(ctx, challenge_id)
        if challenge is None:
            raise SocialError("challenge not found in profile")
        if challenge.status == "DISMISSED":
            raise SocialError("dismissed challenges cannot be reviewed")
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
        stmt = select(FactualityChallenge).where(
            FactualityChallenge.workspace_id == ctx.workspace_id,
            FactualityChallenge.profile_id == ctx.profile_id,
        )
        if status:
            stmt = stmt.where(FactualityChallenge.status == status)
        return list(
            self.session.scalars(stmt.order_by(FactualityChallenge.created_at.desc()))
        )
