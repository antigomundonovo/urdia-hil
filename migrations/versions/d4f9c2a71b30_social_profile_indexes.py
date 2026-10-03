"""Index profile-scoped social queries.

Adds profile indexes to factuality challenges and social inbox items.
"""

from typing import Sequence, Union

revision: str = "d4f9c2a71b30"
down_revision: Union[str, None] = "b31c7f8e4a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Retained as a historical revision after the profile indexes were
    # consolidated into b31c7f8e4a21. Intentionally no-op to keep upgrades
    # from attempting to create duplicate indexes on fresh databases.
    pass


def downgrade() -> None:
    # The indexes belong to b31c7f8e4a21 and must remain owned by that
    # revision when this later historical revision is downgraded.
    pass
