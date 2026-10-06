"""User terms-of-use acceptance (Emenda 014 follow-up, dono 2026-10-06).

Records when (and which version of) the Terms of Use the user accepted at
registration. NULL = accepted before this field existed.

Revision ID: b7c9d1e3f5a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c9d1e3f5a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("terms_version", sa.String(32)))


def downgrade() -> None:
    op.drop_column("users", "terms_version")
    op.drop_column("users", "terms_accepted_at")
