"""core registry fields (Doc 00 §24 — Provider/Capability Registry:
provider, capability, version, schema, quota, cost, privacy, license,
health, fallback, allowed profiles)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("version", sa.String(length=64), nullable=True))
    op.add_column("providers", sa.Column("privacy", postgresql.JSONB(), nullable=True))
    op.add_column("providers", sa.Column("license", sa.String(length=128), nullable=True))
    op.add_column("providers", sa.Column("health", sa.String(length=32), nullable=True))
    op.add_column("providers", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("providers", sa.Column("config", postgresql.JSONB(), nullable=True))

    op.add_column("capabilities", sa.Column("schema", postgresql.JSONB(), nullable=True))
    op.add_column("capabilities", sa.Column("quota", postgresql.JSONB(), nullable=True))
    op.add_column("capabilities", sa.Column("cost", postgresql.JSONB(), nullable=True))
    op.add_column(
        "capabilities",
        sa.Column("fallback_provider_id", sa.Uuid(), nullable=True),
    )
    op.add_column("capabilities", sa.Column("allowed_profiles", postgresql.JSONB(), nullable=True))
    op.add_column("capabilities", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_capabilities_fallback_provider",
        "capabilities",
        "providers",
        ["fallback_provider_id"],
        ["id"],
    )
    op.create_index("ix_capabilities_key", "capabilities", ["key"])


def downgrade() -> None:
    op.drop_index("ix_capabilities_key", table_name="capabilities")
    op.drop_constraint("fk_capabilities_fallback_provider", "capabilities", type_="foreignkey")
    op.drop_column("capabilities", "last_verified_at")
    op.drop_column("capabilities", "allowed_profiles")
    op.drop_column("capabilities", "fallback_provider_id")
    op.drop_column("capabilities", "cost")
    op.drop_column("capabilities", "quota")
    op.drop_column("capabilities", "schema")
    op.drop_column("providers", "config")
    op.drop_column("providers", "last_verified_at")
    op.drop_column("providers", "health")
    op.drop_column("providers", "license")
    op.drop_column("providers", "privacy")
    op.drop_column("providers", "version")
