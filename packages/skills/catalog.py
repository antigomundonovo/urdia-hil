"""Skill catalog (AMENDMENT-2026-10-01-012): the ten owner-declared skills,
each delegating to an EXISTING handler/service. DECLARED skills are
documented but intentionally unimplemented in V1 (see docstrings)."""

from __future__ import annotations

import json
from typing import Any

from packages.skills.base import (
    NullProgress,
    SkillDefinition,
    SkillError,
    SkillRegistry,
)


def _invoke_handler(module: str, name: str, ctx, payload: dict[str, Any]) -> dict:
    import importlib

    handler = getattr(importlib.import_module(module), name)
    return dict(handler(ctx, payload, NullProgress()) or {})


def _llm_available() -> bool:
    from packages.shared.settings import get_settings

    return bool(get_settings().google_ai_api_key)


# --- implemented skills (delegate to real handlers) --------------------------


def _research(ctx, payload):
    return _invoke_handler("apps.worker.handlers", "discovery_scan", ctx, payload)


def _factuality(ctx, payload):
    return _invoke_handler("apps.worker.handlers", "claim_verification", ctx, payload)


def _scripting(ctx, payload):
    if not _llm_available():
        raise SkillError(
            "scripting requires GOOGLE_AI_API_KEY (Copywriter LLM) — configure "
            "the key or use the manual draft flow"
        )
    return _invoke_handler(
        "apps.worker.handlers_real", "CONTENT_GENERATION", ctx, payload
    )


def _image_inspection(ctx, payload):
    return _invoke_handler(
        "apps.worker.handlers_real", "IMAGE_ANALYSIS", ctx, payload
    )


def _platform_policy(ctx, payload):
    """Check-only publisher gate: reports what would pass/fail, changes nothing."""
    import uuid as uuidlib

    from packages.domain.editorial import ContentPackage
    from packages.research.content import ContentService
    from packages.shared.db import SessionLocal

    package_id = payload.get("package_id")
    if not package_id:
        raise SkillError("platform_policy requires package_id")
    from pathlib import Path

    from packages.shared.settings import get_settings

    settings = get_settings()
    with SessionLocal() as session:
        package = session.get(ContentPackage, uuidlib.UUID(str(package_id)))
        if package is None or package.workspace_id != ctx.workspace_id:
            raise SkillError("content package not found in workspace")
        checks = ContentService(
            session,
            export_root=Path(settings.export_root),
            asset_root=Path(settings.asset_root),
        ).publisher_gate(ctx, package, str(payload.get("platform", "")))
        session.commit()
    return {
        "package_id": str(package.id),
        "platform": payload.get("platform"),
        "checks": checks,
        "would_pass": all(checks.values()),
    }


def _publication(ctx, payload):
    """Export a READY package; the run STOPS here — human confirm moves
    PENDING -> PUBLISHED (Amendment 007). Never auto-publishes."""
    return _invoke_handler("apps.worker.handlers_real", "EXPORT", ctx, payload)


def _analytics(ctx, payload):
    return _invoke_handler("apps.worker.handlers_real", "ANALYTICS_SYNC", ctx, payload)


def _factuality_challenge(ctx, payload):
    """Run the judge over a factuality challenge (contract §11): maps the
    deterministic verdict onto the challenge. Evidence itself is gathered
    through registered sources (research sweep / add_evidence)."""
    if not payload.get("challenge_id"):
        raise SkillError("factuality_challenge requires challenge_id")
    from packages.research.social import SocialError, SocialIntelligenceService
    from packages.shared.db import SessionLocal

    with SessionLocal() as session:
        service = SocialIntelligenceService(session)
        try:
            challenge = service.research_challenge(ctx, payload["challenge_id"])
            session.commit()
        except SocialError as exc:
            raise SkillError(f"factuality_challenge: {exc}") from exc
        return {
            "challenge_id": str(challenge.id),
            "status": challenge.status,
            "verdict": challenge.verdict,
            "verdict_reason": challenge.verdict_reason,
        }


# --- declared skills (documented, unimplemented in V1) -----------------------


def _not_implemented(key: str, reason: str):
    def _fn(ctx, payload):
        raise SkillError(f"skill {key} is DECLARED but not implemented in V1: {reason}")

    return _fn


def build_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        SkillDefinition(
            key="research",
            name="Research Reach",
            description="Varre fontes registradas (incl. YouTube) e coleta itens novos",
            required_payload_keys=("workspace_id", "profile_id"),
            invoke=_research,
        )
    )
    registry.register(
        SkillDefinition(
            key="factuality",
            name="Evidence Analyzer",
            description="Recomputa vereditos determinísticos das claims do perfil",
            required_payload_keys=("workspace_id", "profile_id"),
            invoke=_factuality,
        )
    )
    registry.register(
        SkillDefinition(
            key="scripting",
            name="Editorial Scripting",
            description="Propõe rascunho via Copywriter (LLM) — sempre passa por revisão humana",
            required_payload_keys=("package_id",),
            invoke=_scripting,
        )
    )
    registry.register(
        SkillDefinition(
            key="image_inspection",
            name="Image Inspection",
            description="Hashes + classificação visual proposta (Doc 10)",
            required_payload_keys=("asset_ids",),
            invoke=_image_inspection,
        )
    )
    registry.register(
        SkillDefinition(
            key="platform_policy",
            name="Platform Policy",
            description="Roda o publisher gate em modo consulta (check-only)",
            required_payload_keys=("package_id",),
            invoke=_platform_policy,
        )
    )
    registry.register(
        SkillDefinition(
            key="publication",
            name="Publication",
            description="Exporta pacote READY; termina em PENDING p/ confirm humano",
            required_payload_keys=("package_id", "platform"),
            invoke=_publication,
        )
    )
    registry.register(
        SkillDefinition(
            key="factuality_challenge",
            name="Factuality Challenge",
            description="Julga desafio factual de comentário via judge determinístico (§11)",
            required_payload_keys=("challenge_id",),
            invoke=_factuality_challenge,
        )
    )
    registry.register(
        SkillDefinition(
            key="analytics",
            name="Analytics",
            description="Registra métricas (import manual) — histórico anexado",
            required_payload_keys=("publication_id", "metrics"),
            invoke=_analytics,
        )
    )
    for key, reason in (
        ("visual_direction", "render roda dentro do export (Doc 13)"),
        ("seo", "SEO vem do CopywriterSEO no payload do draft"),
        ("music", "voice-over/trilha são V2 (Doc 13)"),
    ):
        registry.register(
            SkillDefinition(
                key=key,
                name=key.replace("_", " ").title(),
                description=f"DECLARED (AMENDMENT-012): {reason}",
                required_payload_keys=(),
                invoke=_not_implemented(key, reason),
                status="DECLARED",
            )
        )
    return registry


def skill_contracts() -> str:
    """Human-readable summary of every skill contract (ops/debug)."""
    lines = []
    for skill in build_skill_registry()._skills.values():
        lines.append(
            json.dumps(
                {
                    "key": skill.key,
                    "status": skill.status,
                    "description": skill.description,
                    "required_payload": list(skill.required_payload_keys),
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)
