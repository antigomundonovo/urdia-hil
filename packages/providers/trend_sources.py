"""Music Trend Intelligence — fontes de sinal (referência MusicIntelligence
§14-§18).

REGRA ABSOLUTA: nunca fabricar sinal. Fonte sem API oficial acessível =
UNAVAILABLE (o adapter reporta, o sistema registra e segue). Não criar
dependência de scraping frágil; não assumir APIs que não existem.
TREND SIGNAL ≠ LICENSE: nenhum adapter atribui direitos.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from packages.contracts.music import TrendSignal

PLATFORMS = ("instagram", "facebook", "youtube", "tiktok", "kwai")

# TTL de freshness por fonte (referência §51) — configurável por decisão
# editorial quando fontes reais entrarem; conservador por padrão.
DEFAULT_FRESHNESS_TTL = {"tiktok": 6, "instagram": 12, "youtube": 24, "facebook": 24, "kwai": 24}


class TrendSourceUnavailable(Exception):
    """TREND_SOURCE_UNAVAILABLE: a fonte não tem API oficial conectada."""


class TrendSourceAdapter(Protocol):
    platform: str

    def fetch(self) -> Sequence[TrendSignal]:
        """Sinais atuais da plataforma (nunca fabricados)."""
        ...


class _UnavailableAdapter:
    """Fonte real ainda não conectada — reporta indisponibilidade.

    Implementações futuras (Creative Center, YouTube Data API, etc.)
    entram aqui respeitando os termos de cada fonte.
    """

    def __init__(self, platform: str):
        self.platform = platform

    def fetch(self) -> Sequence[TrendSignal]:
        raise TrendSourceUnavailable(
            f"TREND_SOURCE_UNAVAILABLE: nenhuma API oficial de {self.platform} "
            "conectada — nenhum sinal fabricado"
        )


def get_adapters() -> dict[str, TrendSourceAdapter]:
    """Adapters por plataforma (referência §5): todas as cinco suportadas
    na arquitetura; hoje todas reportam UNAVAILABLE até haver API oficial
    com credencial (decisão humana)."""
    return {platform: _UnavailableAdapter(platform) for platform in PLATFORMS}


def mark_stale(signal: TrendSignal, *, now: datetime | None = None) -> bool:
    """Freshness (§51): sinal fora do TTL é stale — nunca tratado como atual."""
    now = now or datetime.now(UTC)
    if signal.freshness_expires_at is None:
        return False
    return bool(signal.freshness_expires_at < now)


def components_from_payload(payload: dict[str, Any]) -> TrendSignal:
    """Normaliza um payload externo em TrendSignal validado (§4
    NORMALIZATION). Campos ausentes ficam None/UNKNOWN — nunca inventados."""
    return TrendSignal.model_validate(payload)
