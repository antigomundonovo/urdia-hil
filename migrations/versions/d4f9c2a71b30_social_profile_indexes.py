"""Index profile-scoped social queries.

Adds profile indexes to factuality challenges and social inbox items.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d4f9c2a71b30"
down_revision: Union[str, None] = "b31c7f8e4a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
