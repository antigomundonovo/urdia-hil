"""editorial tables (Doc 04 "Editorial tables"): opportunities,
opportunity_sources, opportunity_claims, opportunity_assets, format_plans,
platform_plans, canonical_contents, content_packages, platform_variants,
drafts

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = 'sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),'
_UPD = 'sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),'


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("why_now", sa.Text(), nullable=True),
        sa.Column("why_profile", sa.Text(), nullable=True),
        sa.Column("editorial_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("risk_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("timing_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("novelty_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opportunities_workspace_id", "opportunities", ["workspace_id"])
    op.create_index("ix_opportunities_profile_id", "opportunities", ["profile_id"])
    op.create_index("ix_opportunities_state", "opportunities", ["state"])

    for table, fk_target in [
        ("opportunity_sources", "sources.id"),
        ("opportunity_claims", "claims.id"),
        ("opportunity_assets", "assets.id"),
    ]:
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("workspace_id", sa.Uuid(), nullable=False),
            sa.Column("opportunity_id", sa.Uuid(), nullable=False),
            sa.Column("ref_id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["ref_id"], [fk_target]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("opportunity_id", "ref_id", name=f"uq_{table}"),
        )

    op.create_table(
        "format_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "platform_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "canonical_contents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("factual_core", postgresql.JSONB(), nullable=True),
        sa.Column("claims", postgresql.JSONB(), nullable=True),
        sa.Column("source_references", postgresql.JSONB(), nullable=True),
        sa.Column("editorial_angle", sa.Text(), nullable=True),
        sa.Column("key_message", sa.Text(), nullable=True),
        sa.Column("visual_assets", postgresql.JSONB(), nullable=True),
        sa.Column("cta_policy", postgresql.JSONB(), nullable=True),
        sa.Column("seo_entities", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "content_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_content_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_content_id"], ["canonical_contents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "platform_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("content_package_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["content_package_id"], ["content_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("content_package_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("claim_ids_used", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["content_package_id"], ["content_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("drafts")
    op.drop_table("platform_variants")
    op.drop_table("content_packages")
    op.drop_table("canonical_contents")
    op.drop_table("platform_plans")
    op.drop_table("format_plans")
    for table in ("opportunity_assets", "opportunity_claims", "opportunity_sources"):
        op.drop_table(table)
    op.drop_index("ix_opportunities_state", table_name="opportunities")
    op.drop_index("ix_opportunities_profile_id", table_name="opportunities")
    op.drop_index("ix_opportunities_workspace_id", table_name="opportunities")
    op.drop_table("opportunities")
