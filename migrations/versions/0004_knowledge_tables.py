"""knowledge tables (Doc 04 "Knowledge tables"): entities, events, stories,
story_entities, story_events, claims, evidence_records, contradictions,
verdicts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UPD = 'sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),'


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("cluster_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["cluster_id"], ["discovery_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stories_workspace_id", "stories", ["workspace_id"])
    op.create_index("ix_stories_status", "stories", ["status"])

    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("external_refs", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_workspace_id", "entities", ["workspace_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_on", sa.String(length=64), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_workspace_id", "events", ["workspace_id"])

    op.create_table(
        "story_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "story_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("story_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=True),
        sa.Column("predicate", sa.String(length=255), nullable=True),
        sa.Column("object", sa.Text(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("claim_type", sa.String(length=64), nullable=True),
        sa.Column("temporal_scope", sa.String(length=128), nullable=True),
        sa.Column("geographic_scope", sa.String(length=128), nullable=True),
        sa.Column("importance", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("interpretation_flag", sa.Boolean(), nullable=True),
        sa.Column("editorial_wording", sa.Text(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_workspace_id", "claims", ["workspace_id"])
    op.create_index("ix_claims_profile_id", "claims", ["profile_id"])
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_story_id", "claims", ["story_id"])

    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_type", sa.String(length=64), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("page_reference", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("snapshot_reference", sa.String(length=512), nullable=True),
        sa.Column("supports", sa.Boolean(), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=True),
        sa.Column("independence_group", sa.String(length=128), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_claim_id", "evidence_records", ["claim_id"])
    op.create_index("ix_evidence_workspace_id", "evidence_records", ["workspace_id"])

    op.create_table(
        "contradictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("supporting_side", postgresql.JSONB(), nullable=True),
        sa.Column("contradicting_side", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contradictions_claim_id", "contradictions", ["claim_id"])

    op.create_table(
        "verdicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("rule_version", sa.String(length=32), nullable=True),
        sa.Column("supporting_groups", sa.Integer(), nullable=True),
        sa.Column("contradicting_sources", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verdicts_claim_id", "verdicts", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_verdicts_claim_id", table_name="verdicts")
    op.drop_table("verdicts")
    op.drop_index("ix_contradictions_claim_id", table_name="contradictions")
    op.drop_table("contradictions")
    op.drop_index("ix_evidence_workspace_id", table_name="evidence_records")
    op.drop_index("ix_evidence_claim_id", table_name="evidence_records")
    op.drop_table("evidence_records")
    op.drop_index("ix_claims_story_id", table_name="claims")
    op.drop_index("ix_claims_status", table_name="claims")
    op.drop_index("ix_claims_profile_id", table_name="claims")
    op.drop_index("ix_claims_workspace_id", table_name="claims")
    op.drop_table("claims")
    op.drop_table("story_events")
    op.drop_table("story_entities")
    op.drop_index("ix_events_workspace_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_entities_workspace_id", table_name="entities")
    op.drop_table("entities")
    op.drop_index("ix_stories_status", table_name="stories")
    op.drop_index("ix_stories_workspace_id", table_name="stories")
    op.drop_table("stories")
