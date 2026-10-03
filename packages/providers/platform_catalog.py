"""Platform capability catalog (Doc 14): DECLARED descriptors for the seven
owner-approved networks (AMENDMENT-2026-10-01-011).

This is declarative metadata ONLY — no adapter is enabled by default and the
PlatformRegistry stays empty until real credentials are configured and
verified (Doc 14: "só registrar integrações após configurar credenciais
oficiais, validar requisitos/limites documentados e testar revogação").
Sources and per-platform notes: docs/PLATFORM_CAPABILITIES.md.

Policy (owner, 2026-10-01): platforms with an official posting API publish
directly from URDIA — always AFTER human approval (confirm, Amendment 007);
platforms without one get a complete manual-posting kit in the export
bundle (text, media, steps, requirements).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from packages.domain.enums import PublicationMethod


@dataclass(frozen=True)
class DeclaredPlatform:
    """Declared (not yet enabled) platform capabilities per Doc 14."""

    key: str
    display_name: str
    publication_method: PublicationMethod  # target method once configured
    capabilities: tuple[str, ...]
    requirements: tuple[str, ...]
    limits: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    researched_on: date | None = None


PLATFORM_CATALOG: tuple[DeclaredPlatform, ...] = (
    DeclaredPlatform(
        key="instagram",
        display_name="Instagram",
        publication_method=PublicationMethod.API,
        capabilities=("publish", "media", "carousel", "analytics"),
        requirements=(
            "conta Instagram Business/Creator",
            "página do Facebook vinculada",
            "app Meta tipo Business (developers.facebook.com)",
        ),
        limits={"api_posts_per_24h": 100, "hashtags_max": 30},
        notes="Graph API Content Publishing: media container -> publish; "
        "carrossel conta como 1 post.",
        researched_on=date(2026, 10, 1),
    ),
    DeclaredPlatform(
        key="facebook",
        display_name="Facebook",
        publication_method=PublicationMethod.API,
        capabilities=("publish", "media", "analytics"),
        requirements=(
            "página do Facebook (perfis pessoais não são suportados pela API)",
            "app Meta com permissões de página",
        ),
        limits={},
        notes="Graph API Page Publishing.",
        researched_on=date(2026, 10, 1),
    ),
    DeclaredPlatform(
        key="x",
        display_name="X (Twitter)",
        publication_method=PublicationMethod.API,
        capabilities=("publish", "media", "analytics"),
        requirements=(
            "conta de desenvolvedor X",
            "créditos pay-per-use (sem tier gratuito para postar)",
        ),
        limits={"cost_per_post_usd": 0.015, "cost_per_post_with_link_usd": 0.20},
        notes="API v2 pay-per-use (modelos Free/Basic/Pro aposentados para "
        "novos desenvolvedores em 2026).",
        researched_on=date(2026, 10, 1),
    ),
    DeclaredPlatform(
        key="youtube",
        display_name="YouTube",
        publication_method=PublicationMethod.API,
        capabilities=("video_upload", "analytics"),
        requirements=(
            "projeto Google Cloud verificado",
            "OAuth 2.0 com escopo youtube.upload",
            "vídeo para uploads (posts de comunidade NÃO têm API -> manual)",
        ),
        limits={"quota_units_per_upload": 1600, "default_daily_quota": 10000},
        notes="Data API v3 videos.insert (~6 uploads/dia no quota default). "
        "Posts de Comunidade: MANUAL/EXPORT (Doc 14).",
        researched_on=date(2026, 10, 1),
    ),
    DeclaredPlatform(
        key="tiktok",
        display_name="TikTok",
        publication_method=PublicationMethod.API,
        capabilities=("video_upload", "analytics"),
        requirements=(
            "app registrado no TikTok for Developers com escopo video.publish",
            "auditoria de app aprovada para Direct Post "
            "(sem auditoria o post sai privado/apenas para si)",
        ),
        limits={},
        notes="Content Posting API (Direct Post requer auditoria; unchecked "
        "posts ficam self-only).",
        researched_on=date(2026, 10, 1),
    ),
    DeclaredPlatform(
        key="threads",
        display_name="Threads",
        publication_method=PublicationMethod.API,
        capabilities=("publish", "media", "analytics"),
        requirements=("app Threads com OAuth (Client ID/Secret, escopos)",),
        limits={"text_max_chars": 500, "api_posts_per_24h": 250},
        notes="Threads API: media container -> threads_publish.",
        researched_on=date(2026, 10, 1),
    ),
    DeclaredPlatform(
        key="kwai",
        display_name="Kwai",
        publication_method=PublicationMethod.MANUAL,
        capabilities=("manual_export",),
        requirements=(
            "postagem pelo app Kwai ou Kwai Creator Center",
            "sem API pública de publicação (apenas APIs de ads e leitura "
            "não-oficiais) — confirmado em 2026-10-01",
        ),
        limits={},
        notes="Mesma regra do YouTube Community (Doc 14): MANUAL/EXPORT até "
        "que exista API oficial adequada. O export gera kit de postagem "
        "manual completo.",
        researched_on=date(2026, 10, 1),
    ),
)

_CATALOG_BY_KEY = {p.key: p for p in PLATFORM_CATALOG}

# Keys accepted for PlatformPlan/export per the owner-approved list.
ALLOWED_PLATFORM_KEYS = frozenset(_CATALOG_BY_KEY)


def get_declared(key: str) -> DeclaredPlatform | None:
    return _CATALOG_BY_KEY.get(key)


def posting_method(key: str) -> PublicationMethod:
    """Target publication method for a platform (API where an official
    posting API exists, MANUAL otherwise). Unknown keys -> MANUAL."""
    declared = _CATALOG_BY_KEY.get(key)
    return declared.publication_method if declared else PublicationMethod.MANUAL
