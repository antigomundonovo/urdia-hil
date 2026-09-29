"""SQLAlchemy models — core tables (Doc 04 "Core tables").

Column lists follow Doc 04 where specified (profiles, jobs, audit_events).
For tables whose columns the spec does not enumerate (users, workspaces,
workspace_members, providers, capabilities, job_steps) the model carries the
minimum identity/scoping/timestamp columns required by the conventions
(UUID ids, TIMESTAMPTZ, workspace/profile scoping); they are extended by new
migrations when their feature milestones specify more.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.domain.enums import JobType
from packages.shared.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(String(255))


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class WorkspaceMember(Base, TimestampMixin):
    __tablename__ = "workspace_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)


class Profile(Base, TimestampMixin):
    """Fields per Doc 04. Unique: (workspace_id, key)."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16))
    audience_region: Mapped[str | None] = mapped_column(String(64))
    editorial_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    visual_identity: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    content_taxonomy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    platform_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    risk_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cta_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    seo_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    automation_level: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_profile_workspace_key"),)


class Provider(Base, TimestampMixin):
    """Provider Registry (Doc 00 §24) — minimal identity now, registry fields
    extended at the governance milestone."""

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(32))


class Capability(Base, TimestampMixin):
    """Capability Registry (Doc 00 §24) — minimal identity now."""

    __tablename__ = "capabilities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))


class Job(Base, TimestampMixin):
    """Fields per Doc 04. status values are fixed at the jobs milestone (step 13);
    Doc 07 already requires recognizing RUNNING for checkpoint recovery."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    job_type: Mapped[JobType] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    priority: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    attempt: Mapped[int | None] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int | None] = mapped_column(Integer)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_jobs_workspace_id", "workspace_id"),
        Index("ix_jobs_profile_id", "profile_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created_at", "created_at"),
    )


class JobStep(Base, TimestampMixin):
    __tablename__ = "job_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (Index("ix_job_steps_job_id", "job_id"),)


class AuditEvent(Base, TimestampMixin):
    """Fields per Doc 04. Append-only for normal use (Doc 08): no update/delete
    paths are provided by the application; corrections create new events."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(64))
    new_state: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[Any] | None] = mapped_column(JSONB)
    rule_version: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(128))
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    __table_args__ = (
        Index("ix_audit_workspace_id", "workspace_id"),
        Index("ix_audit_profile_id", "profile_id"),
        Index("ix_audit_timestamp", "timestamp"),
    )
