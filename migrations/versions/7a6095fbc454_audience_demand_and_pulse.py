"""Audience demands + pulses (contract §10; rebuilt after corruption).

O arquivo original foi gravado com bytes nulos por uma ferramenta externa
(OpenCode) e nunca chegou a ser aplicado via alembic (alembic_version
ficou em 0010; as tabelas foram criadas fora do alembic e foram
removidas vazias para recriacao canonica). Esta versao reescreve a
migracao fielmente a partir de packages/domain/social.py.

Revision ID: 7a6095fbc454
Revises: 87bdb2df4fab
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7a6095fbc454"
down_revision: Union[str, None] = "87bdb2df4fab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audience_demands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column(
            "unique_people_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("growth", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("engagement", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("platforms", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("editorial_fit", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audience_demands_workspace", "audience_demands", ["workspace_id"]
    )

    op.create_table(
        "audience_pulses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("topic_clusters", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audience_pulses_workspace", "audience_pulses", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audience_pulses_workspace", table_name="audience_pulses")
    op.drop_table("audience_pulses")
    op.drop_index("ix_audience_demands_workspace", table_name="audience_demands")
    op.drop_table("audience_demands")
