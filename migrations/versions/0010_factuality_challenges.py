"""Factuality challenges (AMENDMENT-2026-10-02-013, contract §11).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "factuality_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
        sa.Column(
            "comment_id",
            sa.Uuid(),
            sa.ForeignKey("comments.id"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), sa.ForeignKey("claims.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PROPOSED"),
        sa.Column("verdict", sa.String(length=32), nullable=True),
        sa.Column("verdict_reason", sa.Text(), nullable=True),
        sa.Column("verdict_metadata", sa.JSON(), nullable=True),
        sa.Column("researched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_factuality_challenges_workspace", "factuality_challenges", ["workspace_id"]
    )
    op.create_index(
        "ix_factuality_challenges_comment", "factuality_challenges", ["comment_id"]
    )
    op.create_index(
        "ix_factuality_challenges_status", "factuality_challenges", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_factuality_challenges_status", table_name="factuality_challenges")
    op.drop_index("ix_factuality_challenges_comment", table_name="factuality_challenges")
    op.drop_index(
        "ix_factuality_challenges_workspace", table_name="factuality_challenges"
    )
    op.drop_table("factuality_challenges")
