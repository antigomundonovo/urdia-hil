"""Knowledge models (Doc 04 "Knowledge tables", Docs 12/13/16).

Claims carry the exact Doc 04 fields; evidence_records likewise. The core
epistemology of the Constitution lives here:
CLAIM → EVIDENCE → SOURCE → PROVENANCE (Doc 00 §12); a claim's status is
NEVER asserted by an LLM — it is computed deterministically from evidence by
packages.research.verification (Doc 17 §10: prompt is not governance).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.domain.enums import UncertaintyState
from packages.shared.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Story(Base):
    """Story = a history potentially told (Doc 00 §10)."""

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="DRAFT")
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discovery_clusters.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_stories_workspace_id", "workspace_id"),
        Index("ix_stories_status", "status"),
    )


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    external_refs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_entities_workspace_id", "workspace_id"),)


class HistoricalEvent(Base):
    """Table name `events` (Doc 04); `Event` collides with nothing but reads
    ambiguously, so the model is HistoricalEvent."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_events_workspace_id", "workspace_id"),)


class StoryEntity(Base):
    __tablename__ = "story_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StoryEvent(Base):
    __tablename__ = "story_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Claim(Base):
    """Fields per Doc 04. Status computed only by the deterministic verifier."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    story_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stories.id"))
    subject: Mapped[str | None] = mapped_column(String(512))
    predicate: Mapped[str | None] = mapped_column(String(255))
    object: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    claim_type: Mapped[str | None] = mapped_column(String(64))
    temporal_scope: Mapped[str | None] = mapped_column(String(128))
    geographic_scope: Mapped[str | None] = mapped_column(String(128))
    importance: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[UncertaintyState] = mapped_column(String(32), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    interpretation_flag: Mapped[bool | None] = mapped_column(Boolean)
    editorial_wording: Mapped[str | None] = mapped_column(Text)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_claims_workspace_id", "workspace_id"),
        Index("ix_claims_profile_id", "profile_id"),
        Index("ix_claims_status", "status"),
        Index("ix_claims_story_id", "story_id"),
    )


class EvidenceRecord(Base):
    """Fields per Doc 04. `supports=True` supports the claim, `False`
    contradicts it — both sides are preserved (Doc 16)."""

    __tablename__ = "evidence_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"))
    evidence_type: Mapped[str | None] = mapped_column(String(64))
    excerpt: Mapped[str | None] = mapped_column(Text)
    page_reference: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2048))
    snapshot_reference: Mapped[str | None] = mapped_column(String(512))
    supports: Mapped[bool] = mapped_column(Boolean, nullable=False)
    strength: Mapped[int | None] = mapped_column(Integer)
    independence_group: Mapped[str | None] = mapped_column(String(128))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_evidence_claim_id", "claim_id"),
        Index("ix_evidence_workspace_id", "workspace_id"),
    )


class Contradiction(Base):
    """Preserves both sides of a conflict (Doc 13/16)."""

    __tablename__ = "contradictions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    supporting_side: Mapped[list[Any] | None] = mapped_column(JSONB)
    contradicting_side: Mapped[list[Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_contradictions_claim_id", "claim_id"),)


class Verdict(Base):
    """Append-only history of deterministic assessments (corrections create
    new verdicts — history is never rewritten, Doc 15)."""

    __tablename__ = "verdicts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    verdict: Mapped[UncertaintyState] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str | None] = mapped_column(String(32))
    supporting_groups: Mapped[int | None] = mapped_column(Integer)
    contradicting_sources: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_verdicts_claim_id", "claim_id"),)
