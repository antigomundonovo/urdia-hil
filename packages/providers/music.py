"""MusicProvider abstraction (Emenda 014 §20; referência MusicIntelligence
§25/§29).

Nenhum fornecedor único é acoplado. Implementação padrão (`catalog`)
consulta o catálogo local `music_tracks`. NUNCA inventar música,
artista, licença, URL ou direito. TREND SIGNAL ≠ LICENSE.

Códigos de erro explícitos (referência §54): MUSIC_RIGHTS_UNKNOWN,
MUSIC_RIGHTS_BLOCKED, MUSIC_PLATFORM_SCOPE_MISMATCH, MUSIC_LICENSE_EXPIRED,
MUSIC_TERRITORY_NOT_ALLOWED, STUDIO_GATEWAY_UNAVAILABLE.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.audio import MusicTrack
from packages.shared.settings import get_settings

# Licenças que o HIL aceita como suficientemente seguras para uso.
# LICENSE_UNKNOWN NUNCA entra aqui (fail-closed).
SAFE_LICENSE_TYPES = frozenset(
    {"ROYALTY_FREE", "CREATIVE_COMMONS", "PUBLIC_DOMAIN", "COMMERCIAL", "PLATFORM_SPECIFIC"}
)

# rights_state publicável condicional: PLATFORM_LIMITED só com a
# plataforma explicitamente em allowed_platforms (referência §29)
USABLE_RIGHTS_STATES = frozenset({"ORIGINAL", "LICENSED", "PLATFORM_LIMITED"})


class StudioGatewayUnavailable(Exception):
    """STUDIO_GATEWAY_UNAVAILABLE: o contrato com o Studio ainda não
    existe em produção — o sistema reporta indisponível, nunca inventa."""


class MusicProvider(Protocol):
    def search(
        self,
        session: Session,
        workspace_id: Any,
        *,
        mood: str | None = None,
        intensity: str | None = None,
        instrumental: bool | None = None,
        language_code: str | None = None,
        platform: str | None = None,
        min_duration_seconds: int | None = None,
    ) -> list[MusicTrack]:
        """Tracks candidatas do catálogo (validação final é fail-closed)."""
        ...

    def validate_usage(
        self,
        track: MusicTrack,
        *,
        platform: str,
        territory: str | None = None,
        at: datetime | None = None,
    ) -> tuple[bool, str]:
        """(apto, código) — fail-closed: UNKNOWN/BLOCKED nunca são seguros."""
        ...


class CatalogMusicProvider:
    """Fonte = catálogo local do workspace (music_tracks)."""

    def search(
        self,
        session: Session,
        workspace_id: Any,
        *,
        mood: str | None = None,
        intensity: str | None = None,
        instrumental: bool | None = None,
        language_code: str | None = None,
        platform: str | None = None,
        min_duration_seconds: int | None = None,
    ) -> list[MusicTrack]:
        stmt = select(MusicTrack).where(MusicTrack.workspace_id == workspace_id)
        tracks = list(session.scalars(stmt))
        candidates: list[MusicTrack] = []
        for track in tracks:
            if track.rights_state not in USABLE_RIGHTS_STATES:
                continue
            if instrumental is not None and bool(track.is_instrumental) is not instrumental:
                continue
            # Música vocal em idioma diferente do conteúdo não é escolhida
            # sem decisão editorial (referência §21); instrumental não é
            # limitado por idioma.
            if (
                language_code
                and not track.is_instrumental
                and track.music_language_code
                and track.music_language_code != language_code
            ):
                continue
            if min_duration_seconds and (track.duration_seconds or 0) < min_duration_seconds:
                continue
            if platform and track.allowed_platforms and platform not in track.allowed_platforms:
                continue
            candidates.append(track)

        # determinístico: mood exato, depois intensidade, depois
        # instrumental, depois mais recentes
        def _key(track: MusicTrack):
            return (
                0 if (mood and track.mood == mood) else 1,
                0 if (intensity and track.intensity == intensity) else 1,
                0 if track.is_instrumental else 1,
                -(track.created_at.timestamp() if track.created_at else 0),
            )

        return sorted(candidates, key=_key)

    def validate_usage(
        self,
        track: MusicTrack,
        *,
        platform: str,
        territory: str | None = None,
        at: datetime | None = None,
    ) -> tuple[bool, str]:
        at = at or datetime.now(UTC)
        if track.rights_state == "BLOCKED":
            return False, "MUSIC_RIGHTS_BLOCKED"
        if track.rights_state == "UNKNOWN":
            return False, "MUSIC_RIGHTS_UNKNOWN"
        if track.rights_state not in USABLE_RIGHTS_STATES:
            return False, "MUSIC_RIGHTS_UNKNOWN"
        if track.license_type == "LICENSE_UNKNOWN":
            return False, "MUSIC_RIGHTS_UNKNOWN"
        if track.license_type not in SAFE_LICENSE_TYPES:
            return False, f"MUSIC_LICENSE_NOT_SAFE:{track.license_type}"
        if track.rights_state == "PLATFORM_LIMITED" and (
            not track.allowed_platforms or platform not in track.allowed_platforms
        ):
            # PLATFORM_LIMITED ≠ GLOBAL (referência §57.2/§29)
            return False, "MUSIC_PLATFORM_SCOPE_MISMATCH"
        if track.license_expires_at is not None:
            expires = track.license_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < at:
                return False, "MUSIC_LICENSE_EXPIRED"
        if track.allowed_platforms and platform not in track.allowed_platforms:
            return False, "MUSIC_PLATFORM_SCOPE_MISMATCH"
        if territory and track.allowed_territories and territory not in track.allowed_territories:
            return False, "MUSIC_TERRITORY_NOT_ALLOWED"
        return True, "OK"


class StudioMusicGateway:
    """Contrato para consumir MusicPlan/MusicAsset do Studio
    (referência §22/§25/§43). A API do Studio ainda NÃO existe —
    a implementação real reporta indisponibilidade em vez de inventar."""

    def get_music_plan(self, music_plan_id: str) -> dict[str, Any]:
        raise StudioGatewayUnavailable(
            "STUDIO_GATEWAY_UNAVAILABLE: contrato MusicPlan do Studio ainda não implementado"
        )

    def get_music_asset(self, music_asset_id: str) -> dict[str, Any]:
        raise StudioGatewayUnavailable(
            "STUDIO_GATEWAY_UNAVAILABLE: contrato MusicAsset do Studio ainda não implementado"
        )


_PROVIDER_KEY = "catalog"


def get_music_provider() -> MusicProvider:
    """Seleção por configuração (hoje só `catalog`; futuras fontes entram
    aqui sem tocar no resto do sistema)."""
    settings = get_settings()
    chosen = getattr(settings, "music_provider", _PROVIDER_KEY) or _PROVIDER_KEY
    if chosen != "catalog":
        raise ValueError(f"music provider desconhecido: {chosen!r}")
    return CatalogMusicProvider()
