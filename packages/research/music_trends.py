"""Music Trend Intelligence service (referência MusicIntelligence §4-§13).

Cadeia: PLATFORM SIGNALS → SOURCE ADAPTERS → NORMALIZATION →
FRESHNESS + PROVENANCE → TREND DETECTION (estados explicáveis) →
CROSS-PLATFORM CORRELATION (por DNA, nunca por nome) → consulta pelo
resto do sistema. Sem ML agora (referência §38); TREND SIGNAL ≠ LICENSE.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.contracts.music import TrendSignal
from packages.domain.audio import MusicTrendSignal
from packages.governance.audit import append_audit
from packages.providers.trend_sources import (
    DEFAULT_FRESHNESS_TTL,
    PLATFORMS,
    TrendSourceUnavailable,
    get_adapters,
    mark_stale,
)
from packages.shared.execution_context import ExecutionContext


class TrendError(Exception):
    """Erro explícito da camada de tendências (código na mensagem)."""


def derive_state(signal: TrendSignal) -> tuple[str, list[str]]:
    """Estado de tendência determinístico e EXPLICÁVEL (referência §13).

    Componentes separados → estado + razões; nenhum score opaco.
    """
    c = signal.components
    reasons: list[str] = []
    if signal.rights_state in {"UNKNOWN", "BLOCKED"}:
        reasons.append(f"rights_state={signal.rights_state} (TREND SIGNAL ≠ LICENSE)")
        return "RIGHTS_BLOCKED", reasons

    spread = c.cross_platform_spread or 0
    velocity = c.velocity
    saturation = c.saturation
    popularity = c.popularity

    if saturation is not None and saturation >= 0.8:
        reasons.append(f"saturação {saturation:.2f} ≥ 0.80")
        state = "HUGE_SATURATED"
    elif velocity is not None and velocity < 0:
        reasons.append(f"velocidade {velocity:.2f} < 0 (decaindo)")
        state = "DECAYING"
    elif velocity is not None and velocity >= 0.5 and (popularity or 0) < 0.4:
        reasons.append(
            f"velocidade {velocity:.2f} ≥ 0.50 com popularidade {(popularity or 0):.2f} < 0.40"
        )
        state = "EMERGING"
    elif spread >= 2:
        reasons.append(f"presente em {spread} plataformas (correlação por DNA)")
        state = "CROSS_PLATFORM"
    else:
        reasons.append(f"local de {signal.source_platform} sem sinais de explosão")
        state = "PLATFORM_LOCAL"
    return state, reasons


def correlate(signals: list[TrendSignal]) -> dict[tuple, list[TrendSignal]]:
    """Correlação cross-platform por assinatura normalizada do MusicDNA
    (referência §11) — NUNCA comparando nome de música."""
    groups: dict[tuple, list[TrendSignal]] = {}
    for signal in signals:
        if signal.music_dna is None:
            continue
        groups.setdefault(signal.music_dna.fingerprint(), []).append(signal)
    return {k: v for k, v in groups.items() if len({s.source_platform for s in v}) >= 2}


class MusicTrendService:
    def __init__(self, session: Session):
        self.session = session
        self.adapters = get_adapters()

    # --- ingestão -------------------------------------------------------------

    def ingest_from_platform(
        self, ctx: ExecutionContext, platform: str
    ) -> dict:
        """Puxa sinais de UMA plataforma via adapter (referência §4).

        Fonte indisponível → resposta honesta TREND_SOURCE_UNAVAILABLE,
        nada persistido, nada inventado.
        """
        if platform not in PLATFORMS:
            raise TrendError(f"plataforma não suportada: {platform!r}")
        adapter = self.adapters[platform]
        try:
            raw_signals = list(adapter.fetch())
        except TrendSourceUnavailable as exc:
            append_audit(
                self.session,
                ctx=ctx,
                action="trend.source.unavailable",
                entity_type="music_trend_source",
                entity_id=None,
                new_state="UNAVAILABLE",
                reason=str(exc),
            )
            return {
                "platform": platform,
                "status": "TREND_SOURCE_UNAVAILABLE",
                "ingested": 0,
                "detail": str(exc),
            }

        ttl_hours = DEFAULT_FRESHNESS_TTL.get(platform, 24)
        now = datetime.now(UTC)
        ingested = 0
        for signal in raw_signals:
            stale = mark_stale(signal, now=now)
            row = MusicTrendSignal(
                workspace_id=ctx.workspace_id,
                source_platform=signal.source_platform,
                source_id=signal.source_id,
                detected_at=signal.detected_at,
                observed_at=signal.observed_at,
                region=signal.region,
                category=signal.category,
                music_reference=signal.music_reference,
                music_dna=signal.music_dna.model_dump() if signal.music_dna else None,
                components=signal.components.model_dump(),
                rights_state=signal.rights_state,
                rights_note=signal.rights_note,
                state=signal.state or derive_state(signal)[0],
                reasons=signal.reasons or derive_state(signal)[1],
                provenance=signal.provenance,
                freshness_expires_at=signal.freshness_expires_at
                or now + timedelta(hours=ttl_hours),
                stale=stale,
            )
            self.session.add(row)
            ingested += 1
            append_audit(
                self.session,
                ctx=ctx,
                action="trend.signal.detected",
                entity_type="music_trend_signal",
                entity_id=row.id,
                new_state=row.state,
                metadata={"platform": platform, "stale": stale},
            )
        self.session.flush()
        return {"platform": platform, "status": "OK", "ingested": ingested}

    # --- consulta ---------------------------------------------------------------

    def list_signals(
        self,
        workspace_id: uuid.UUID,
        *,
        platform: str | None = None,
        include_stale: bool = False,
    ) -> list[MusicTrendSignal]:
        stmt = select(MusicTrendSignal).where(MusicTrendSignal.workspace_id == workspace_id)
        if platform:
            stmt = stmt.where(MusicTrendSignal.source_platform == platform)
        rows = list(self.session.scalars(stmt.order_by(MusicTrendSignal.observed_at.desc())))
        if not include_stale:
            rows = [row for row in rows if not row.stale]
        return rows

    def cross_platform_correlations(self, workspace_id: uuid.UUID) -> dict[tuple, int]:
        """Grupos de sinais que aparecem em ≥2 plataformas com o mesmo
        DNA normalizado (referência §11)."""
        rows = self.list_signals(workspace_id)
        signals = [
            TrendSignal(
                trend_signal_id=str(row.id),
                source_platform=row.source_platform,
                source_id=row.source_id,
                detected_at=row.detected_at,
                observed_at=row.observed_at,
                music_dna=row.music_dna,
                components=row.components or {},
                rights_state=row.rights_state,
                state=row.state,
                reasons=row.reasons or [],
                provenance=row.provenance or {},
            )
            for row in rows
            if row.music_dna
        ]
        from packages.contracts.music import MusicDNA, TrendComponents

        rebuilt: list[TrendSignal] = []
        for signal in signals:
            signal.music_dna = MusicDNA.model_validate(signal.music_dna)
            signal.components = TrendComponents.model_validate(signal.components)
            rebuilt.append(signal)
        return {key: len(group) for key, group in correlate(rebuilt).items()}
