"""Add profile scope to Social/Audience Intelligence tables.

Revision ID: b31c7f8e4a21
Revises: 7a6095fbc454
Create Date: 2026-10-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b31c7f8e4a21"
down_revision: Union[str, None] = "7a6095fbc454"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("audience_demands", "audience_pulses"):
        op.add_column(
            table,
            sa.Column(
                "profile_id",
                sa.Uuid(),
                sa.ForeignKey("profiles.id"),
                nullable=True,
            ),
        )
        op.create_index(
            f"ix_{table}_profile",
            table,
            ["profile_id"],
        )

    op.create_index(
        "ix_factuality_challenges_profile",
        "factuality_challenges",
        ["profile_id"],
    )
    op.create_index(
        "ix_social_inbox_items_profile",
        "social_inbox_items",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_social_inbox_items_profile",
        table_name="social_inbox_items",
    )
    op.drop_index(
        "ix_factuality_challenges_profile",
        table_name="factuality_challenges",
    )
    for table in ("audience_pulses", "audience_demands"):
        op.drop_index(f"ix_{table}_profile", table_name=table)
        op.drop_column(table, "profile_id")
