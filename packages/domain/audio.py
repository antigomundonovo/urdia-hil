"""Social Audio / Music Intelligence models (Emenda 014; referência
MusicIntelligence; Doc 13).

Música ≠ áudio de vídeo: o plano tem CAMADAS (voice/music/ambient/
effects). Direitos são fail-closed: ORIGINAL/LICENSED/PLATFORM_LIMITED/
UNKNOWN/BLOCKED — UNKNOWN e BLOCKED NUNCA são publicáveis. TREND SIGNAL
≠ LICENSE. Nada aqui publica; o uso de música passa por portão humano.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()

# Estados de direitos (referência §7)
RIGHTS_STATES = ("ORIGINAL", "LICENSED", "PLATFORM_LIMITED", "UNKNOWN", "BLOCKED")
# Estados de plano de áudio (referência §22 + NO_CANDIDATE do seletor)
PLAN_RIGHTS_STATES = ("LICENSED", "PLATFORM_LIMITED", "UNKNOWN", "BLOCKED", "NO_CANDIDATE")


class MusicTrack(Base):
    """Catálogo de músicas do workspace (referência §18/§23).

    Metadados só de fonte verificável/provider — NUNCA inventados.
    rights_state nasce UNKNOWN até a licença ser registrada e validada.
    """

    __tablename__ = "music_tracks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(255))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    genre: Mapped[str | None] = mapped_column(String(64))
    mood: Mapped[str | None] = mapped_column(String(64))
    bpm: Mapped[float | None] = mapped_column(Float)
    is_instrumental: Mapped[bool | None] = mapped_column(Boolean)
    # Idioma da MÚSICA (letra) — independente do idioma do conteúdo
    # (referência §21). Instrumental não é limitado por idioma.
    music_language_code: Mapped[str | None] = mapped_column(String(8))
    music_locale_code: Mapped[str | None] = mapped_column(String(16))
    origin: Mapped[str | None] = mapped_column(String(255))
    # ROYALTY_FREE | CREATIVE_COMMONS | PUBLIC_DOMAIN | COMMERCIAL |
    # PLATFORM_SPECIFIC | LICENSE_UNKNOWN
    license_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="LICENSE_UNKNOWN"
    )
    license_notes: Mapped[str | None] = mapped_column(Text)
    attribution_required: Mapped[bool | None] = mapped_column(Boolean)
    # NULL = sem restrição declarada (a licença continua mandando)
    allowed_platforms: Mapped[list[Any] | None] = mapped_column(JSONB)
    allowed_territories: Mapped[list[Any] | None] = mapped_column(JSONB)
    license_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tags: Mapped[list[Any] | None] = mapped_column(JSONB)
    # LOW | MEDIUM | HIGH
    intensity: Mapped[str | None] = mapped_column(String(16))
    version: Mapped[str | None] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    file_hash: Mapped[str | None] = mapped_column(String(128))
    # MusicDNA estruturado (referência §9): genre/bpm/energy/tension/
    # instrumentation/structure/... — ausente = desconhecido, nunca inventado
    dna: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # ORIGINAL | LICENSED | PLATFORM_LIMITED | UNKNOWN | BLOCKED
    rights_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_music_tracks_workspace", "workspace_id"),
        Index("ix_music_tracks_rights_state", "rights_state"),
        Index("ix_music_tracks_mood", "mood"),
    )


class AudioPlan(Base):
    """Plano de áudio de um ContentPackage (referência §22; Emenda 014).

    audio_mode: NONE | MUSIC | AMBIENT | VOICE | MUSIC_AND_VOICE.
    status: SUGGESTED | APPROVED | REJECTED — decisão HUMANA explícita
    (portão), nunca inventada. layers guarda o plano por camada.
    """

    __tablename__ = "audio_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    content_package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_packages.id", ondelete="CASCADE"), nullable=False
    )
    audio_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="NONE")
    # Plano por camadas: {"music": {...}, "voice": {...}, ...}
    layers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Motivo da recomendação (explicabilidade, referência §37)
    reason: Mapped[str | None] = mapped_column(Text)
    # Estado de direitos do plano: LICENSED | PLATFORM_LIMITED |
    # UNKNOWN | BLOCKED | NO_CANDIDATE
    rights_state: Mapped[str | None] = mapped_column(String(32))
    platform_constraints: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Portão humano
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUGGESTED")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_audio_plans_workspace", "workspace_id"),
        Index("ix_audio_plans_package", "content_package_id"),
        Index("ix_audio_plans_rights_state", "rights_state"),
    )


class MusicTrendSignal(Base):
    """Sinal de tendência musical com proveniência (referência §10).

    TREND SIGNAL ≠ LICENSE: rights_state é dimensão separada; sinal
    UNKNOWN/BLOCKED nunca vira uso. Sinal stale (freshness expirado)
    não é tratado como atual. Fonte sem API oficial = nenhum sinal
    (nunca fabricado).
    """

    __tablename__ = "music_trend_signals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(64))
    music_reference: Mapped[str | None] = mapped_column(Text)
    music_dna: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Componentes SEPARADOS (referência §12) — proibido score único opaco
    components: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rights_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    rights_note: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(32))
    reasons: Mapped[list[Any] | None] = mapped_column(JSONB)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    freshness_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_music_trend_signals_workspace", "workspace_id"),
        Index("ix_music_trend_signals_platform", "source_platform"),
        Index("ix_music_trend_signals_state", "state"),
    )
