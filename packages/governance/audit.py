"""Audit appender (Doc 05: every capability call ends in audit; Doc 08:
audit is append-only for normal use)."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from packages.domain.repositories import AuditRepository
from packages.shared.execution_context import ExecutionContext


def append_audit(
    session: Session,
    *,
    ctx: ExecutionContext,
    action: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    new_state: str | None = None,
    reason: str | None = None,
    rule_version: str | None = None,
    provider: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    return AuditRepository(session).append(
        workspace_id=ctx.workspace_id,
        profile_id=ctx.profile_id,
        actor_id=ctx.actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        new_state=new_state,
        reason=reason,
        rule_version=rule_version,
        provider=provider,
        metadata=metadata,
    )
