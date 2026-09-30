"""Editorial models (Doc 04 "Editorial tables", Doc 12, Doc 00 §10-11).

Opportunity is the central unit; state column tracks the Doc 00 §26 machine
via TransitionService. Canonical Content carries the Doc 00 §11 fields.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Opportunity(Base):
    """Fields per Doc 04 (+ `state` for the Doc 03 machine)."""

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    story_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stories.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    why_now: Mapped[str | None] = mapped_column(Text)
    why_profile: Mapped[str | None] = mapped_column(Text)
    editorial_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    risk_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timing_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    novelty_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision: Mapped[str | None] = mapped_column(String(32))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="DISCOVERED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_opportunities_workspace_id", "workspace_id"),
        Index("ix_opportunities_profile_id", "profile_id"),
        Index("ix_opportunities_state", "state"),
    )


def _link_table(name: str, ref_table: str):
    class _Link(Base):
        __tablename__ = name
        __table_args__ = (
            UniqueConstraint("opportunity_id", "ref_id", name=f"uq_{name}"),
        )

        id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
        workspace_id: Mapped[uuid.UUID] = mapped_column(
            ForeignKey("workspaces.id"), nullable=False
        )
        opportunity_id: Mapped[uuid.UUID] = mapped_column(
            ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
        )
        ref_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ref_table), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        )

    _Link.__name__ = name.capitalize()
    return _Link


# Doc 04 lists the three link tables explicitly; dynamic class creation keeps
# them in one place with identical shape.
OpportunitySource = _link_table("opportunity_sources", "sources.id")
OpportunityClaim = _link_table("opportunity_claims", "claims.id")
OpportunityAsset = _link_table("opportunity_assets", "assets.id")


class FormatPlan(Base):
    __tablename__ = "format_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlatformPlan(Base):
    __tablename__ = "platform_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CanonicalContent(Base):
    """Doc 00 §11 canonical fields — every format starts from here."""

    __tablename__ = "canonical_contents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    factual_core: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    claims: Mapped[list[Any] | None] = mapped_column(JSONB)
    source_references: Mapped[list[Any] | None] = mapped_column(JSONB)
    editorial_angle: Mapped[str | None] = mapped_column(Text)
    key_message: Mapped[str | None] = mapped_column(Text)
    visual_assets: Mapped[list[Any] | None] = mapped_column(JSONB)
    cta_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    seo_entities: Mapped[list[Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContentPackage(Base):
    __tablename__ = "content_packages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    canonical_content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_contents.id"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlatformVariant(Base):
    __tablename__ = "platform_variants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    content_package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_packages.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    content_package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_packages.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512))
    caption: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    claim_ids_used: Mapped[list[Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
