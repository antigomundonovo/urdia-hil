"""asset + rights tables (Doc 04 "Asset tables"): assets, asset_versions,
rights_records

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("original_file_url", sa.String(length=2048), nullable=True),
        sa.Column("page_url", sa.String(length=2048), nullable=True),
        sa.Column("institution", sa.String(length=255), nullable=True),
        sa.Column("creator", sa.String(length=255), nullable=True),
        sa.Column("creation_date", sa.String(length=64), nullable=True),
        sa.Column("license", sa.String(length=128), nullable=True),
        sa.Column("license_url", sa.String(length=2048), nullable=True),
        sa.Column("attribution_text", sa.Text(), nullable=True),
        sa.Column("retrieval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("perceptual_hash", sa.String(length=64), nullable=True),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column("rights_confidence", sa.Integer(), nullable=True),
        sa.Column("visual_classification", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_workspace_id", "assets", ["workspace_id"])
    op.create_index("ix_assets_profile_id", "assets", ["profile_id"])
    op.create_index("ix_assets_file_hash", "assets", ["file_hash"])
    op.create_index("ix_assets_perceptual_hash", "assets", ["perceptual_hash"])
    op.create_index("ix_assets_status", "assets", ["status"])

    op.create_table(
        "asset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=64), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("tool", sa.String(length=128), nullable=True),
        sa.Column("tool_version", sa.String(length=64), nullable=True),
        sa.Column("visual_classification", sa.String(length=32), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["parent_version_id"], ["asset_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_versions_asset_id", "asset_versions", ["asset_id"])

    op.create_table(
        "rights_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("license", sa.String(length=128), nullable=True),
        sa.Column("license_url", sa.String(length=2048), nullable=True),
        sa.Column("rights_holder", sa.String(length=255), nullable=True),
        sa.Column("attribution_required", sa.Boolean(), nullable=True),
        sa.Column("attribution_text", sa.Text(), nullable=True),
        sa.Column("territory", sa.String(length=64), nullable=True),
        sa.Column("commercial_use", sa.Boolean(), nullable=True),
        sa.Column("modification_allowed", sa.Boolean(), nullable=True),
        sa.Column("evidence_source_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["evidence_source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rights_asset_id", "rights_records", ["asset_id"])
    op.create_index("ix_rights_status", "rights_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_rights_status", table_name="rights_records")
    op.drop_index("ix_rights_asset_id", table_name="rights_records")
    op.drop_table("rights_records")
    op.drop_index("ix_asset_versions_asset_id", table_name="asset_versions")
    op.drop_table("asset_versions")
    op.drop_index("ix_assets_status", table_name="assets")
    op.drop_index("ix_assets_perceptual_hash", table_name="assets")
    op.drop_index("ix_assets_file_hash", table_name="assets")
    op.drop_index("ix_assets_profile_id", table_name="assets")
    op.drop_index("ix_assets_workspace_id", table_name="assets")
    op.drop_table("assets")
