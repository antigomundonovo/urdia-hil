"""Auxiliary structured memory (Doc 05 §Memory; V2.2 Hermes).

Revision ID: a8b7c6d5e4f3
Revises: f1a2b3c4d5e6
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b7c6d5e4f3"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "superseded_by", sa.Uuid(), sa.ForeignKey("agent_memories.id"), nullable=True
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index("ix_agent_memories_workspace", "agent_memories", ["workspace_id"])
    op.create_index("ix_agent_memories_kind", "agent_memories", ["kind"])
    op.create_index("ix_agent_memories_status", "agent_memories", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_memories_status", table_name="agent_memories")
    op.drop_index("ix_agent_memories_kind", table_name="agent_memories")
    op.drop_index("ix_agent_memories_workspace", table_name="agent_memories")
    op.drop_table("agent_memories")
