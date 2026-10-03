"""social inbox items (UHL-4: Social Inbox)

Revision ID: 87bdb2df4fab
Revises: 0010
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '87bdb2df4fab'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_inbox_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
        sa.Column("comment_id", sa.Uuid(), sa.ForeignKey("comments.id"), nullable=True),
        sa.Column("item_type", sa.String(length=32), nullable=False, server_default="COMMENT"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="UNREAD"),
        sa.Column("assigned_to", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("suggested_reply", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_inbox_items_workspace", "social_inbox_items", ["workspace_id"])
    op.create_index("ix_social_inbox_items_status", "social_inbox_items", ["status"])
    op.create_index("ix_social_inbox_items_comment", "social_inbox_items", ["comment_id"])


def downgrade() -> None:
    op.drop_index("ix_social_inbox_items_comment", table_name="social_inbox_items")
    op.drop_index("ix_social_inbox_items_status", table_name="social_inbox_items")
    op.drop_index("ix_social_inbox_items_workspace", table_name="social_inbox_items")
    op.drop_table("social_inbox_items")
