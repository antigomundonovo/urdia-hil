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
    email: Mapped[str | None] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(512))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)


class AuthSession(Base, TimestampMixin):
    """Opaque, revocable URDIA login session; only a token digest is persisted."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )


class AuthActionToken(Base, TimestampMixin):
    """One-time email verification or password-reset token digest."""

    __tablename__ = "auth_action_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_action_tokens_hash"),
        Index("ix_auth_action_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_auth_action_tokens_expires_at", "expires_at"),
    )


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


class MachineClient(Base, TimestampMixin):
    """API key client for the Studio⇄HIL bridge (Emenda 002: auth
    máquina-a-máquina + allowlist). Only a token digest is persisted; the
    raw key is shown once at creation. Machine clients can only reach the
    bridge router — the allowlist is the router itself."""

    __tablename__ = "machine_clients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_machine_clients_key_hash"),
        Index("ix_machine_clients_workspace", "workspace_id"),
    )


class Profile(Base, TimestampMixin):
    """Fields per Doc 04. Unique: (workspace_id, key)."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Legado (formato livre, ex. "pt-BR"). Contrato canônico (Emenda 014):
    # language_code + locale_code.
    language: Mapped[str | None] = mapped_column(String(16))
    language_code: Mapped[str | None] = mapped_column(String(8))
    locale_code: Mapped[str | None] = mapped_column(String(16))
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
    """Provider Registry (Doc 00 §24): provider, version, privacy, license,
    health, last_verified. Config carries non-secret settings only (Doc 08)."""

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))
    privacy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    license: Mapped[str | None] = mapped_column(String(128))
    health: Mapped[str | None] = mapped_column(String(32))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Capability(Base, TimestampMixin):
    """Capability Registry (Doc 00 §24): version, schema, quota, cost,
    fallback, allowed profiles. allowed_profiles stores profile keys;
    NULL/empty list = allowed for every profile (documented decision —
    fail-closed still applies to status/health/quota)."""

    __tablename__ = "capabilities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    fallback_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("providers.id")
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))
    schema_: Mapped[dict[str, Any] | None] = mapped_column("schema", JSONB)
    quota: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    allowed_profiles: Mapped[list[Any] | None] = mapped_column(JSONB)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_capabilities_key", "key"),)


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


# --- Research tables (Doc 04 "Research tables", Doc 09) -------------------


class Source(Base, TimestampMixin):
    """Fields per Doc 04."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    publisher: Mapped[str | None] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_proximity: Mapped[str | None] = mapped_column(String(32))
    # Idioma da FONTE (legado + contrato canônico, Emenda 014). Não é o
    # idioma do conteúdo de destino — esse vive em canonical_contents etc.
    language: Mapped[str | None] = mapped_column(String(16))
    language_code: Mapped[str | None] = mapped_column(String(8))
    locale_code: Mapped[str | None] = mapped_column(String(16))
    jurisdiction: Mapped[str | None] = mapped_column(String(64))
    access_type: Mapped[str | None] = mapped_column(String(32))
    archive_status: Mapped[str | None] = mapped_column(String(32))
    reliability_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correction_history: Mapped[list[Any] | None] = mapped_column(JSONB)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_sources_workspace_id", "workspace_id"),
        Index("ix_sources_profile_id", "profile_id"),
        Index("ix_sources_canonical_url", "canonical_url"),
        Index("ix_sources_status", "status"),
    )


class Retrieval(Base, TimestampMixin):
    """Observability per fetch (Doc 09: registrar query/source, duração,
    resultados, erros). Append-only history — never overwritten."""

    __tablename__ = "retrievals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(128))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    item_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    __table_args__ = (
        Index("ix_retrievals_source_id", "source_id"),
        Index("ix_retrievals_created_at", "created_at"),
    )


class SourceRelation(Base, TimestampMixin):
    """Dependency chains (Doc 09): A cita B, B reproduz C — clusters, never
    counted as independent confirmations."""

    __tablename__ = "source_relations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    related_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_source_relations_source_id", "source_id"),)


class DiscoveryCluster(Base, TimestampMixin):
    __tablename__ = "discovery_clusters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    label: Mapped[str | None] = mapped_column(String(512))
    item_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_discovery_clusters_workspace_id", "workspace_id"),)


class DiscoveryItem(Base, TimestampMixin):
    __tablename__ = "discovery_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"))
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discovery_clusters.id"))
    url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NORMALIZED")
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_discovery_items_workspace_id", "workspace_id"),
        Index("ix_discovery_items_status", "status"),
        Index("ix_discovery_items_content_hash", "content_hash"),
    )


class AgentMemory(Base, TimestampMixin):
    """Auxiliary structured memory (Doc 05 §Memory; V2.2 Hermes). Auxiliary
    only — never a canonical factual source (Emenda 002). FACT entries must
    carry origin (source + provenance); enforced fail-closed in the service."""

    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance: {"source_type": ..., "source_id": ..., "url": ...,
    # "recorded_by": ...} — required for FACT (Doc 05: "toda memória
    # factual deve possuir origem").
    origin: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE"
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_memories.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_agent_memories_workspace", "workspace_id"),
        Index("ix_agent_memories_kind", "kind"),
        Index("ix_agent_memories_status", "status"),
    )
