"""Human decision on audience demands (contrato §10, V2.1b).

Revision ID: c9d8e7f6a5b4
Revises: a8b7c6d5e4f3
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = "a8b7c6d5e4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audience_demands",
        sa.Column("decision", sa.String(16), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "audience_demands", sa.Column("decided_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "audience_demands",
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id")),
    )
    op.create_index(
        "ix_audience_demands_decision", "audience_demands", ["decision"]
    )


def downgrade() -> None:
    op.drop_index("ix_audience_demands_decision", table_name="audience_demands")
    op.drop_column("audience_demands", "decided_by")
    op.drop_column("audience_demands", "decided_at")
    op.drop_column("audience_demands", "decision")
