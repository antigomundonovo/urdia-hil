"""Learning (Doc 17 step 28; Doc 15 pipeline).

DATA → EXPERIENCE → HYPOTHESIS → EXPERIMENT → RESULT → RULE_CANDIDATE →
HUMAN REVIEW → ACTIVE_RULE

Fail-closed rules implemented here:
- a rule can only be ACTIVATED after an explicit HUMAN REVIEW record
  (activation without review is refused);
- one successful post never becomes a permanent rule (Doc 17 §18): rules
  originate from experiments with recorded results, or from explicitly
  declared experience — never from a single data point;
- private learning stays in the profile (scope=PROFILE); SHARED scope
  requires the generalization milestone and is refused in V1.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import Profile
from packages.domain.publishing import Experiment, ExperimentVariant, LearningRecord, Rule
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext


class LearningError(Exception):
    """Fail closed on learning-governance violations."""


class LearningService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _require_profile(self, ctx: ExecutionContext) -> None:
        if ctx.profile_id is None:
            raise LearningError("learning requires a profile scope")
        profile_id = self.session.scalars(
            select(Profile.id).where(
                Profile.id == ctx.profile_id,
                Profile.workspace_id == ctx.workspace_id,
            )
        ).first()
        if profile_id is None:
            raise LearningError("profile not found in workspace")

    def _experiment_for_context(
        self, ctx: ExecutionContext, experiment: Experiment
    ) -> Experiment:
        self._require_profile(ctx)
        scoped = self.session.scalars(
            select(Experiment).where(
                Experiment.id == experiment.id,
                Experiment.workspace_id == ctx.workspace_id,
                Experiment.profile_id == ctx.profile_id,
            )
        ).first()
        if scoped is None:
            raise LearningError("experiment not found in profile")
        return scoped

    def _rule_for_context(self, ctx: ExecutionContext, rule: Rule) -> Rule:
        self._require_profile(ctx)
        scoped = self.session.scalars(
            select(Rule).where(
                Rule.id == rule.id,
                Rule.workspace_id == ctx.workspace_id,
                Rule.profile_id == ctx.profile_id,
            )
        ).first()
        if scoped is None:
            raise LearningError("rule not found in profile")
        return scoped

    # --- experiments ---------------------------------------------------------

    def create_experiment(
        self,
        ctx: ExecutionContext,
        *,
        hypothesis: str,
        variants: dict[str, dict],
    ) -> Experiment:
        """An experiment declares a hypothesis and at least a control/variant
        pair (Doc 15 experiment model)."""
        self._require_profile(ctx)
        if not hypothesis or not hypothesis.strip():
            raise LearningError("experiment requires a hypothesis")
        if len(variants) < 2:
            raise LearningError("experiment requires at least 2 variants (control + variant)")
        experiment = Experiment(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            hypothesis=hypothesis,
        )
        self.session.add(experiment)
        self.session.flush()
        for key, payload in variants.items():
            self.session.add(
                ExperimentVariant(
                    workspace_id=ctx.workspace_id,
                    experiment_id=experiment.id,
                    variant_key=key,
                    payload=payload,
                )
            )
        self.session.flush()
        self.record_experience(
            ctx, kind="EXPERIMENT", observation=hypothesis,
            hypothesis=hypothesis,
        )
        return experiment

    def record_result(
        self,
        ctx: ExecutionContext,
        experiment: Experiment,
        result: dict,
        decision: str | None = None,
    ) -> Experiment:
        experiment = self._experiment_for_context(ctx, experiment)
        experiment.result = result
        experiment.status = "COMPLETED"
        experiment.decision = decision
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="EXPERIMENT_RESULT",
            entity_type="experiment",
            entity_id=experiment.id,
            new_state="COMPLETED",
        )
        return experiment

    # --- experience / records -------------------------------------------------

    def record_experience(
        self,
        ctx: ExecutionContext,
        *,
        kind: str,
        observation: str | None,
        hypothesis: str | None = None,
    ) -> LearningRecord:
        self._require_profile(ctx)
        record = LearningRecord(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            kind=kind,
            observation=observation,
            hypothesis=hypothesis,
            scope="PROFILE",  # SHARED refused in V1 (generalization milestone)
        )
        self.session.add(record)
        self.session.flush()
        return record

    # --- rules (the human gate) -------------------------------------------------

    def propose_rule(
        self,
        ctx: ExecutionContext,
        *,
        statement: str,
        origin_experiment_id=None,
    ) -> Rule:
        """RULE_CANDIDATE — born CANDIDATE, never active (Doc 15)."""
        self._require_profile(ctx)
        if not statement or not statement.strip():
            raise LearningError("rule requires a statement")
        if origin_experiment_id is not None:
            experiment = self.session.scalars(
                select(Experiment).where(
                    Experiment.id == origin_experiment_id,
                    Experiment.workspace_id == ctx.workspace_id,
                    Experiment.profile_id == ctx.profile_id,
                )
            ).first()
            if experiment is None:
                raise LearningError("origin experiment not found in profile")
            if experiment.status != "COMPLETED" or experiment.result is None:
                raise LearningError("origin experiment must have a recorded result")
        rule = Rule(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            statement=statement,
            status="CANDIDATE",
            origin_experiment_id=origin_experiment_id,
        )
        self.session.add(rule)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="RULE_PROPOSED",
            entity_type="rule",
            entity_id=rule.id,
            new_state="CANDIDATE",
        )
        return rule

    def review_rule(
        self, ctx: ExecutionContext, rule: Rule, *, reviewed_by, notes: str | None = None
    ) -> Rule:
        """HUMAN REVIEW step (Doc 15). Records who reviewed."""
        self._require_profile(ctx)
        rule = self._rule_for_context(ctx, rule)
        if rule.status != "CANDIDATE":
            raise LearningError(f"rule cannot be reviewed from status {rule.status}")
        rule.status = "REVIEWED"
        rule.reviewed_by = reviewed_by
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="RULE_REVIEWED",
            entity_type="rule",
            entity_id=rule.id,
            previous_state="CANDIDATE",
            new_state="REVIEWED",
            reason=notes,
        )
        return rule

    def activate_rule(self, ctx: ExecutionContext, rule: Rule) -> Rule:
        """ACTIVE_RULE — only after REVIEW (fail closed)."""
        self._require_profile(ctx)
        rule = self._rule_for_context(ctx, rule)
        if rule.status != "REVIEWED":
            raise LearningError(
                f"rule cannot be activated from status {rule.status}: "
                "human review required (Doc 15)"
            )
        rule.status = "ACTIVE"
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="RULE_ACTIVATED",
            entity_type="rule",
            entity_id=rule.id,
            previous_state="REVIEWED",
            new_state="ACTIVE",
        )
        return rule

    def list_state(self, workspace_id, profile_id) -> dict:
        profile_exists = self.session.scalars(
            select(Profile.id).where(
                Profile.id == profile_id,
                Profile.workspace_id == workspace_id,
            )
        ).first()
        if profile_exists is None:
            raise LearningError("profile not found in workspace")
        experiments = list(
            self.session.scalars(
                select(Experiment).where(
                    Experiment.workspace_id == workspace_id,
                    Experiment.profile_id == profile_id,
                )
            )
        )
        rules = list(
            self.session.scalars(
                select(Rule).where(
                    Rule.workspace_id == workspace_id,
                    Rule.profile_id == profile_id,
                )
            )
        )
        return {
            "experiments": [
                {
                    "id": str(e.id),
                    "hypothesis": e.hypothesis,
                    "status": e.status,
                    "decision": e.decision,
                    "result": e.result,
                }
                for e in experiments
            ],
            "rules": [
                {"id": str(r.id), "statement": r.statement, "status": r.status}
                for r in rules
            ],
        }
