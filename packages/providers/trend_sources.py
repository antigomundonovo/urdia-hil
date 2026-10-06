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

import httpx

from packages.contracts.music import TrendComponents, TrendSignal

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

    Implementações futuras (Creative Center, Research API, etc.)
    entram aqui respeitando os termos de cada fonte.
    """

    def __init__(self, platform: str):
        self.platform = platform

    def fetch(self) -> Sequence[TrendSignal]:
        raise TrendSourceUnavailable(
            f"TREND_SOURCE_UNAVAILABLE: nenhuma API oficial de {self.platform} "
            "conectada — nenhum sinal fabricado"
        )


class YouTubeTrendAdapter:
    """YouTube Data API v3 — `videos.list(chart=mostPopular)`.

    API oficial e documentada; só precisa de uma API key gratuita do
    Google Cloud (settings.youtube_api_key). Sem chave → UNAVAILABLE.

    HONESTIDADE dos dados: o YouTube não expõe MusicDNA da trilha —
    então dna fica None e confidence é baixa (sinal bruto, referência
    §14: dado não disponível = UNKNOWN, nunca inventado). rights_state
    nasce UNKNOWN SEMPRE (TREND SIGNAL ≠ LICENSE).
    """

    platform = "youtube"

    def fetch(self) -> Sequence[TrendSignal]:
        from packages.shared.settings import get_settings

        settings = get_settings()
        if not settings.youtube_api_key:
            raise TrendSourceUnavailable(
                "TREND_SOURCE_UNAVAILABLE: YOUTUBE_API_KEY não configurada "
                "(só existe API oficial com chave do Google Cloud)"
            )
        region = settings.youtube_trend_region or "BR"
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "chart": "mostPopular",
                "regionCode": region,
                "videoCategoryId": "10",  # Music
                "maxResults": 25,
                "part": "snippet,statistics",
                "key": settings.youtube_api_key,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise TrendSourceUnavailable(
                f"TREND_SOURCE_UNAVAILABLE: YouTube Data API respondeu "
                f"HTTP {resp.status_code}"
            )
        items = resp.json().get("items", [])
        now = datetime.now(UTC)
        max_views = max(
            (int(i.get("statistics", {}).get("viewCount", 0)) for i in items), default=0
        )
        signals: list[TrendSignal] = []
        for item in items:
            video_id = item.get("id", "")
            snippet = item.get("snippet", {})
            views = int(item.get("statistics", {}).get("viewCount", 0))
            published_raw = snippet.get("publishedAt")
            try:
                observed = (
                    datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                    if published_raw
                    else now
                )
            except ValueError:
                observed = now
            signals.append(
                TrendSignal(
                    trend_signal_id=f"youtube:{video_id}",
                    source_platform="youtube",
                    source_id=video_id,
                    detected_at=now,
                    observed_at=observed,
                    region=region,
                    category="music",
                    music_reference=snippet.get("title"),
                    music_dna=None,  # YouTube não expõe DNA — não inventar
                    components=TrendComponents(
                        popularity=(views / max_views) if max_views else None,
                        confidence=0.3,  # sinal bruto de fonte única
                        freshness=1.0,
                    ),
                    rights_state="UNKNOWN",
                    rights_note="sinal de tendência não é licença",
                    state="RIGHTS_BLOCKED",
                    reasons=["rights UNKNOWN: TREND SIGNAL ≠ LICENSE"],
                    provenance={
                        "source": "youtube_data_api_v3",
                        "chart": "mostPopular",
                        "video_category": "10",
                        "fetched_at": now.isoformat(),
                    },
                )
            )
        return signals


def get_adapters() -> dict[str, TrendSourceAdapter]:
    """Adapters por plataforma (referência §5): todas as cinco suportadas
    na arquitetura. YouTube usa a API oficial quando há chave; as demais
    reportam UNAVAILABLE até existir API oficial com credencial (decisão
    humana)."""
    from packages.shared.settings import get_settings

    youtube: TrendSourceAdapter = (
        YouTubeTrendAdapter() if get_settings().youtube_api_key else _UnavailableAdapter("youtube")
    )
    return {
        "instagram": _UnavailableAdapter("instagram"),
        "facebook": _UnavailableAdapter("facebook"),
        "youtube": youtube,
        "tiktok": _UnavailableAdapter("tiktok"),
        "kwai": _UnavailableAdapter("kwai"),
    }


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
