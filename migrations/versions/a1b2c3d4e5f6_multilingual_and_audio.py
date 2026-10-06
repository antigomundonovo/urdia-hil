"""Multilingual contract (Emenda 014) + social audio/music system.

Adds canonical language_code/locale_code columns (backfilled from legacy
`language` without destroying data) and creates music_tracks + audio_plans.

Revision ID: a1b2c3d4e5f6
Revises: c9d8e7f6a5b4
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from packages.multilingual.normalize import LanguageError, normalize_language_tag

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c9d8e7f6a5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_TABLES = ("profiles", "sources")


def _backfill_language(table: str, conn: sa.Connection) -> None:
    """Legacy 'pt-BR' -> language_code='pt' + locale_code='pt-br'.

    Non-parseable legacy values stay untouched (NULL canonical columns);
    nothing is destroyed.
    """
    rows = conn.execute(
        sa.text(
            f"SELECT id, language FROM {table} "
            "WHERE language IS NOT NULL AND language_code IS NULL"
        )
    ).fetchall()
    for row_id, legacy in rows:
        try:
            lang, locale = normalize_language_tag(legacy)
        except LanguageError:
            continue
        conn.execute(
            sa.text(
                f"UPDATE {table} SET language_code=:lang, locale_code=:locale "
                "WHERE id=:id"
            ),
            {"lang": lang, "locale": locale, "id": row_id},
        )


def upgrade() -> None:
    # --- language columns (Emenda 014 §1/§7) ---
    for table in _LEGACY_TABLES + (
        "canonical_contents",
        "content_packages",
        "platform_variants",
        "publications",
        "audience_demands",
    ):
        op.add_column(table, sa.Column("language_code", sa.String(8)))
        op.add_column(table, sa.Column("locale_code", sa.String(16)))
    # source ≠ target (referência §47): até existir adaptação real,
    # target = language_code/locale_code e source fica NULL.
    for table in ("content_packages", "publications"):
        op.add_column(table, sa.Column("source_language_code", sa.String(8)))
        op.add_column(table, sa.Column("source_locale_code", sa.String(16)))
        op.add_column(table, sa.Column("target_language_code", sa.String(8)))
        op.add_column(table, sa.Column("target_locale_code", sa.String(16)))

    # --- publication audio result (Emenda 014 §5/§31) ---
    op.add_column("publications", sa.Column("audio_mode", sa.String(32)))
    op.add_column("publications", sa.Column("audio_applied", sa.Boolean()))
    op.add_column("publications", sa.Column("audio_detail", sa.JSON()))

    # --- music catalog + audio plans (Emenda 014 §18/§22) ---
    op.create_table(
        "music_tracks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("artist", sa.String(255)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("genre", sa.String(64)),
        sa.Column("mood", sa.String(64)),
        sa.Column("bpm", sa.Float()),
        sa.Column("is_instrumental", sa.Boolean()),
        # Idioma da MÚSICA (letra), independente do idioma do conteúdo
        # (referência MusicIntelligence §21).
        sa.Column("music_language_code", sa.String(8)),
        sa.Column("music_locale_code", sa.String(16)),
        sa.Column("origin", sa.String(255)),
        sa.Column("license_type", sa.String(32), nullable=False, server_default="LICENSE_UNKNOWN"),
        # MusicDNA estruturado (referência §9): genre/bpm/energy/... —
        # campos desconhecidos ficam ausentes, nunca inventados.
        sa.Column("dna", sa.JSON()),
        sa.Column("license_notes", sa.Text()),
        sa.Column("attribution_required", sa.Boolean()),
        sa.Column("allowed_platforms", sa.JSON()),
        sa.Column("allowed_territories", sa.JSON()),
        sa.Column("license_expires_at", sa.DateTime(timezone=True)),
        sa.Column("tags", sa.JSON()),
        sa.Column("intensity", sa.String(16)),
        sa.Column("version", sa.String(64)),
        sa.Column("storage_path", sa.String(1024)),
        sa.Column("file_hash", sa.String(128)),
        # Estados de direitos (referência §7): UNKNOWN/BLOCKED nunca
        # são publicáveis; ORIGINAL/LICENSED passam por validação dinâmica
        # (expiração/plataforma/território) no momento do uso.
        sa.Column("rights_state", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_music_tracks_workspace", "music_tracks", ["workspace_id"])
    op.create_index("ix_music_tracks_rights_state", "music_tracks", ["rights_state"])
    op.create_index("ix_music_tracks_mood", "music_tracks", ["mood"])

    op.create_table(
        "audio_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_package_id",
            sa.Uuid(),
            sa.ForeignKey("content_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("audio_mode", sa.String(32), nullable=False, server_default="NONE"),
        sa.Column("layers", sa.JSON()),
        sa.Column("reason", sa.Text()),
        sa.Column("platform_constraints", sa.JSON()),
        # Portão humano (status) + estado de direitos do plano (rights_state)
        sa.Column("status", sa.String(32), nullable=False, server_default="SUGGESTED"),
        sa.Column("rights_state", sa.String(32)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_audio_plans_workspace", "audio_plans", ["workspace_id"])
    op.create_index("ix_audio_plans_package", "audio_plans", ["content_package_id"])
    op.create_index("ix_audio_plans_rights_state", "audio_plans", ["rights_state"])


    op.create_table(
        "music_trend_signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_platform", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(255)),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("region", sa.String(64)),
        sa.Column("category", sa.String(64)),
        sa.Column("music_reference", sa.Text()),
        sa.Column("music_dna", sa.JSON()),
        sa.Column("components", sa.JSON()),
        sa.Column("rights_state", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("rights_note", sa.Text()),
        sa.Column("state", sa.String(32)),
        sa.Column("reasons", sa.JSON()),
        sa.Column("provenance", sa.JSON()),
        sa.Column("freshness_expires_at", sa.DateTime(timezone=True)),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_music_trend_signals_workspace", "music_trend_signals", ["workspace_id"])
    op.create_index("ix_music_trend_signals_platform", "music_trend_signals", ["source_platform"])
    op.create_index("ix_music_trend_signals_state", "music_trend_signals", ["state"])

    # --- legacy backfill (Emenda 014 §11: não destruir informação) ---
    conn = op.get_bind()
    for table in _LEGACY_TABLES:
        _backfill_language(table, conn)


def downgrade() -> None:
    op.drop_index("ix_music_trend_signals_state", table_name="music_trend_signals")
    op.drop_index("ix_music_trend_signals_platform", table_name="music_trend_signals")
    op.drop_index("ix_music_trend_signals_workspace", table_name="music_trend_signals")
    op.drop_table("music_trend_signals")
    for table in ("content_packages", "publications"):
        op.drop_column(table, "target_locale_code")
        op.drop_column(table, "target_language_code")
        op.drop_column(table, "source_locale_code")
        op.drop_column(table, "source_language_code")
    op.drop_index("ix_audio_plans_rights_state", table_name="audio_plans")
    op.drop_index("ix_audio_plans_package", table_name="audio_plans")
    op.drop_index("ix_audio_plans_workspace", table_name="audio_plans")
    op.drop_table("audio_plans")
    op.drop_index("ix_music_tracks_mood", table_name="music_tracks")
    op.drop_index("ix_music_tracks_rights_state", table_name="music_tracks")
    op.drop_index("ix_music_tracks_workspace", table_name="music_tracks")
    op.drop_table("music_tracks")
    for column in ("audio_detail", "audio_applied", "audio_mode"):
        op.drop_column("publications", column)
    for table in (
        "audience_demands",
        "publications",
        "platform_variants",
        "content_packages",
        "canonical_contents",
    ) + _LEGACY_TABLES:
        op.drop_column(table, "locale_code")
        op.drop_column(table, "language_code")
