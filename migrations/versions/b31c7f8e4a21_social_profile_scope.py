"""Add profile isolation to social audience tables.

Legacy audience rows may predate profile scoping, so profile_id remains nullable
at the database level. The application treats NULL as legacy/unscoped and never
returns such rows from profile-scoped reads. All newly created rows require a
profile context and persist profile_id.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b31c7f8e4a21"
down_revision: Union[str, None] = "7a6095fbc454"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audience_demands",
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
    )
    op.create_index(
        "ix_audience_demands_profile",
        "audience_demands",
        ["profile_id"],
    )

    op.add_column(
        "audience_pulses",
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
    )
    op.create_index(
        "ix_audience_pulses_profile",
        "audience_pulses",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audience_pulses_profile", table_name="audience_pulses")
    op.drop_column("audience_pulses", "profile_id")
    op.drop_index("ix_audience_demands_profile", table_name="audience_demands")
    op.drop_column("audience_demands", "profile_id")
