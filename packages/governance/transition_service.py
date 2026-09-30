"""Transition Service (Doc 03).

Every transition verifies, in order:
    current state → transition rule → gate status → permission →
    required data → audit
Any failure raises and nothing changes (fail closed). Every accepted
transition writes an append-only audit event.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from packages.domain.enums import OpportunityState
from packages.domain.state_machine import TransitionError, assert_transition
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext


class TransitionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def apply(
        self,
        ctx: ExecutionContext,
        *,
        entity_type: str,
        entity_id: UUID,
        current: OpportunityState,
        target: OpportunityState,
        reason: str | None = None,
        gates_ok: bool = True,
        required_data: dict[str, Any] | None = None,
        rule_version: str = "constitution-1.0",
    ):
        # 1. current/target must be valid states (assert_transition also covers it)
        try:
            OpportunityState(current)
            OpportunityState(target)
        except ValueError as exc:
            raise TransitionError(f"unknown state: {exc}") from exc

        # 2. transition rule
        assert_transition(current, target)

        # 3. gate status — fail closed: gates must be reported as passed
        if not gates_ok:
            raise TransitionError("gate status not satisfied; transition blocked")

        # 4. permission — the caller's workspace context must exist
        if ctx.workspace_id is None:
            raise TransitionError("missing workspace context; transition blocked")
        from packages.domain.models import Workspace

        if self.session.get(Workspace, ctx.workspace_id) is None:
            raise TransitionError("unknown workspace; transition blocked")

        # 5. required data — every declared key must be present and non-empty
        missing = [
            key
            for key, value in (required_data or {}).items()
            if value is None or value == "" or value == []
        ]
        if missing:
            raise TransitionError(f"required data missing: {', '.join(missing)}")

        # 6. audit (append-only)
        return append_audit(
            self.session,
            ctx=ctx,
            action="STATE_TRANSITION",
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=current.value if hasattr(current, "value") else str(current),
            new_state=target.value if hasattr(target, "value") else str(target),
            reason=reason,
            rule_version=rule_version,
        )
