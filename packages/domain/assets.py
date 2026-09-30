"""Asset + rights models (Doc 04 "Asset tables", Docs 10/11).

storage_path is always system-generated (never user-controlled filenames —
Doc 08 path traversal). Transformations create asset_versions with a parent
chain; the original's history is never erased (Doc 11 derived assets).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Asset(Base):
    """Fields per Doc 04 (+ storage_path for safe local persistence)."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_file_url: Mapped[str | None] = mapped_column(String(2048))
    page_url: Mapped[str | None] = mapped_column(String(2048))
    institution: Mapped[str | None] = mapped_column(String(255))
    creator: Mapped[str | None] = mapped_column(String(255))
    creation_date: Mapped[str | None] = mapped_column(String(64))
    license: Mapped[str | None] = mapped_column(String(128))
    license_url: Mapped[str | None] = mapped_column(String(2048))
    attribution_text: Mapped[str | None] = mapped_column(Text)
    retrieval_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    perceptual_hash: Mapped[str | None] = mapped_column(String(64))
    embedding: Mapped[list[Any] | None] = mapped_column(JSONB)
    rights_confidence: Mapped[int | None] = mapped_column(Integer)
    visual_classification: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_assets_workspace_id", "workspace_id"),
        Index("ix_assets_profile_id", "profile_id"),
        Index("ix_assets_file_hash", "file_hash"),
        Index("ix_assets_perceptual_hash", "perceptual_hash"),
        Index("ix_assets_status", "status"),
    )


class AssetVersion(Base):
    """Every transformation is a new version with parent + tool + parameters
    (Doc 10 transformations, Doc 13 determinism)."""

    __tablename__ = "asset_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_versions.id")
    )
    operation: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tool: Mapped[str | None] = mapped_column(String(128))
    tool_version: Mapped[str | None] = mapped_column(String(64))
    visual_classification: Mapped[str | None] = mapped_column(String(32))
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_asset_versions_asset_id", "asset_id"),)


class RightsRecord(Base):
    """Fields per Doc 04. classification is a RightsClassification value; the
    gate (Doc 11) treats UNKNOWN/PROHIBITED/PERMISSION_REQUIRED as BLOCK."""

    __tablename__ = "rights_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    license: Mapped[str | None] = mapped_column(String(128))
    license_url: Mapped[str | None] = mapped_column(String(2048))
    rights_holder: Mapped[str | None] = mapped_column(String(255))
    attribution_required: Mapped[bool | None] = mapped_column(Boolean)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    territory: Mapped[str | None] = mapped_column(String(64))
    commercial_use: Mapped[bool | None] = mapped_column(Boolean)
    modification_allowed: Mapped[bool | None] = mapped_column(Boolean)
    evidence_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id")
    )
    confidence: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_rights_asset_id", "asset_id"),
        Index("ix_rights_status", "status"),
    )
