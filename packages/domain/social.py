"""Social intelligence domain (AMENDMENT-2026-10-02-013): HIL is the
Social/Audience Intelligence layer of the URDIA ecosystem (frontier
contract: docs/CONTRATO_TECNOLOGICO_URDIA.md).

FactualityChallenge (contract §11): a comment MAY raise a factual
challenge, which is then researched through registered sources and judged
by the deterministic verification engine (Doc 16). Absolute rule: a
comment is NEVER evidence by itself — evidence only enters through the
normal research path with provenance.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class FactualityChallenge(Base):
    __tablename__ = "factuality_challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id"), nullable=False
    )
    # the extracted factual statement to be researched (NOT the evidence)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    # claim created to hold the research/evidence trail (Doc 09/16)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    # PROPOSED | RESOLVED | DISMISSED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED")
    # judge mapping: CONFIRMED | DISPUTED | UNSUPPORTED | UNKNOWN
    verdict: Mapped[str | None] = mapped_column(String(32))
    verdict_reason: Mapped[str | None] = mapped_column(Text)
    verdict_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # human review (the gate) — final verdict may adjust the judge's mapping
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_factuality_challenges_workspace", "workspace_id"),
        Index("ix_factuality_challenges_comment", "comment_id"),
        Index("ix_factuality_challenges_status", "status"),
    )

class SocialInboxItem(Base):
    __tablename__ = "social_inbox_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id"), nullable=True
    )
    # Types: COMMENT, MENTION, DM
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, default="COMMENT")
    # Statuses: UNREAD, OPEN, RESOLVED, IGNORED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNREAD")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    suggested_reply: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_social_inbox_items_workspace", "workspace_id"),
        Index("ix_social_inbox_items_status", "status"),
        Index("ix_social_inbox_items_comment", "comment_id"),
    )


class AudienceDemand(Base):
    __tablename__ = "audience_demands"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    # Nullable only for legacy rows created before profile isolation was added.
    # New rows must always carry profile_id and all profile-scoped reads require it.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    unique_people_count: Mapped[int] = mapped_column(nullable=False, default=0)
    growth: Mapped[float] = mapped_column(nullable=False, default=0.0)
    engagement: Mapped[float] = mapped_column(nullable=False, default=0.0)
    platforms: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    editorial_fit: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audience_demands_workspace", "workspace_id"),
        Index("ix_audience_demands_profile", "profile_id"),
    )


class AudiencePulse(Base):
    __tablename__ = "audience_pulses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    # Nullable only for legacy rows. New pulses are always profile-scoped.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    topic_clusters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audience_pulses_workspace", "workspace_id"),
        Index("ix_audience_pulses_profile", "profile_id"),
    )
