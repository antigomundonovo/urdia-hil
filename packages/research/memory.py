"""Auxiliary memory service (Doc 05 §Memory; V2.2 Hermes).

Auxiliary only: entries never become canonical factual sources (Emenda 002).
Fail-closed rule: a FACT without origin is rejected (Doc 05 — "toda memória
factual deve possuir origem"). Corrections supersede: the old entry is marked
SUPERSEDED with a pointer to the replacement (append-only, Doc 08).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.enums import MemoryKind, MemoryStatus
from packages.domain.models import AgentMemory
from packages.shared.execution_context import ExecutionContext


class MemoryError(Exception):
    pass


_KIND_VALUES = {k.value for k in MemoryKind}
_ORIGIN_KEYS = {"source_type", "source_id", "url", "recorded_by"}


def _has_origin(origin: dict | None) -> bool:
    if not origin:
        return False
    return bool(origin.get("source_type") or origin.get("source_id") or origin.get("url"))


class MemoryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def remember(
        self,
        ctx: ExecutionContext,
        *,
        kind: str,
        content: str,
        origin: dict | None = None,
        confidence: float = 0.0,
        actor_id: UUID | None = None,
        profile_id: UUID | None = None,
    ) -> AgentMemory:
        if kind not in _KIND_VALUES:
            raise MemoryError(f"unknown memory kind: {kind}")
        if not content or not content.strip():
            raise MemoryError("content required")
        if kind == MemoryKind.FACT.value and not _has_origin(origin):
            raise MemoryError("FACT requires origin (source_type, source_id or url)")
        if origin and not set(origin).issubset(_ORIGIN_KEYS):
            raise MemoryError(f"origin keys must be within {_ORIGIN_KEYS}")
        if not 0.0 <= confidence <= 1.0:
            raise MemoryError("confidence must be within [0, 1]")
        entry = AgentMemory(
            workspace_id=ctx.workspace_id,
            profile_id=profile_id,
            kind=kind,
            content=content.strip(),
            origin=origin,
            confidence=confidence,
            status=MemoryStatus.ACTIVE.value,
            created_by=actor_id,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def supersede(
        self,
        ctx: ExecutionContext,
        memory_id: UUID,
        *,
        kind: str,
        content: str,
        origin: dict | None = None,
        confidence: float = 0.0,
        actor_id: UUID | None = None,
    ) -> AgentMemory:
        old = self.session.get(AgentMemory, memory_id)
        if old is None or old.workspace_id != ctx.workspace_id:
            raise MemoryError("memory not found in workspace")
        if old.status != MemoryStatus.ACTIVE.value:
            raise MemoryError("only ACTIVE memories can be superseded")
        replacement = self.remember(
            ctx,
            kind=kind,
            content=content,
            origin=origin or old.origin,
            confidence=confidence,
            actor_id=actor_id,
            profile_id=old.profile_id,
        )
        old.status = MemoryStatus.SUPERSEDED.value
        old.superseded_by = replacement.id
        self.session.flush()
        return replacement

    def archive(self, ctx: ExecutionContext, memory_id: UUID) -> AgentMemory:
        old = self.session.get(AgentMemory, memory_id)
        if old is None or old.workspace_id != ctx.workspace_id:
            raise MemoryError("memory not found in workspace")
        old.status = MemoryStatus.ARCHIVED.value
        self.session.flush()
        return old

    def list_active(
        self,
        ctx: ExecutionContext,
        *,
        kind: str | None = None,
        profile_id: UUID | None = None,
        limit: int = 100,
    ) -> list[AgentMemory]:
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.workspace_id == ctx.workspace_id,
                AgentMemory.status == MemoryStatus.ACTIVE.value,
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(limit)
        )
        if kind is not None:
            if kind not in _KIND_VALUES:
                raise MemoryError(f"unknown memory kind: {kind}")
            stmt = stmt.where(AgentMemory.kind == kind)
        if profile_id is not None:
            stmt = stmt.where(AgentMemory.profile_id == profile_id)
        return list(self.session.scalars(stmt).all())
