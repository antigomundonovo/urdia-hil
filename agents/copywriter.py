"""Copywriter agent (Doc 05): LLM-assisted draft proposal with a hard
deterministic gate (Doc 17 §10 — prompt is not governance).

Pipeline (Doc 05): build context → provider call (structured output) →
schema validation (CopywriterOutput) → semantic validation (claims used
must exist, be attached, and be usable verdicts) → hand to the caller.
The output is a PROPOSAL: it becomes a Draft via ContentService.generate_draft
and still goes through QC + human review before anything is published
(automation_level 2).

The provider is injected — tests use a fake; production uses GeminiProvider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.contracts.agents import CopywriterOutput
from packages.domain.enums import UncertaintyState
from packages.domain.knowledge import Claim
from packages.providers.gemini import ProviderError, ProviderUnavailable
from packages.shared.execution_context import ExecutionContext

# Claims usable by the copywriter: verified-possible or better, never
# controversial/unknown (Doc 16 — afirme pouco; CONFIRMED is human-awarded
# but already usable text-wise).
USABLE_VERDICTS = {
    UncertaintyState.POSSIBLE.value,
    UncertaintyState.PROBABLE.value,
    UncertaintyState.CONFIRMED.value,
}

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "copywriter_v1.md"
PROMPT_VERSION = "copywriter_v1"

COPYWRITER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "caption": {"type": "string"},
        "claim_ids_used": {"type": "array", "items": {"type": "string"}},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["index", "text"],
            },
        },
        "microloop_text": {"type": "string"},
        "seo": {
            "type": "object",
            "properties": {
                "entities": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "required": ["title", "caption", "claim_ids_used"],
}


class CopywriterBlocked(Exception):
    """Fail closed: unusable model output or semantic violation."""


def _settings():
    from packages.shared.settings import get_settings

    return get_settings()


def _load_prompt_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise CopywriterBlocked(f"prompt template missing: {TEMPLATE_PATH.name}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_context(session: Session, ctx: ExecutionContext, package) -> dict[str, Any]:
    """Canonical context from the opportunity + attached verified claims."""
    from packages.domain.editorial import (
        CanonicalContent,
        Opportunity,
        OpportunityClaim,
    )

    opp = session.get(Opportunity, package.opportunity_id)
    if opp is None or opp.workspace_id != ctx.workspace_id:
        raise CopywriterBlocked("opportunity not found in workspace")
    canonical = session.scalars(
        select(CanonicalContent).where(
            CanonicalContent.opportunity_id == opp.id,
            CanonicalContent.workspace_id == ctx.workspace_id,
        )
    ).first()

    rows = session.execute(
        select(Claim, OpportunityClaim)
        .join(OpportunityClaim, OpportunityClaim.ref_id == Claim.id)
        .where(
            OpportunityClaim.opportunity_id == opp.id,
            OpportunityClaim.workspace_id == ctx.workspace_id,
            Claim.workspace_id == ctx.workspace_id,
            Claim.profile_id == ctx.profile_id,
        )
    ).all()
    claims: list[dict[str, str]] = []
    for claim, _link in rows:
        claims.append(
            {
                "id": str(claim.id),
                "verdict": claim.status,
                "text": claim.normalized_text
                or " ".join(
                    part
                    for part in (claim.subject, claim.predicate, claim.object)
                    if part
                ),
            }
        )
    return {
        "opportunity_title": opp.title or "",
        "editorial_angle": (canonical.editorial_angle if canonical else "") or "",
        "key_message": (canonical.key_message if canonical else "") or "",
        "format": package.format,
        "claims": claims,
        "language_instruction": _language_instruction(session, ctx, package, canonical),
    }


def _language_instruction(session: Session, ctx: ExecutionContext, package, canonical) -> str:
    """Contrato de idioma (Emenda 014 §8): destino EXPLÍCITO no prompt —
    conteúdo canônico > perfil (configuração editorial) > default
    editorial documentado. Nunca deduzido da plataforma."""
    from packages.domain.models import Profile
    from packages.domain.profile_defaults import DEFAULT_EDITORIAL_POLICY
    from packages.multilingual import LanguageError, describe_pair, normalize_language_tag

    language_code = (canonical.language_code if canonical else None) or package.language_code
    locale_code = (canonical.locale_code if canonical else None) or package.locale_code
    if not language_code and ctx.profile_id:
        profile = session.get(Profile, ctx.profile_id)
        if profile is not None:
            if profile.language_code:
                language_code, locale_code = profile.language_code, profile.locale_code
            elif profile.language:
                try:
                    language_code, locale_code = normalize_language_tag(profile.language)
                except LanguageError:
                    pass
    if not language_code:
        language_code = DEFAULT_EDITORIAL_POLICY["language_code"]
        locale_code = DEFAULT_EDITORIAL_POLICY["locale_code"]
    return describe_pair(language_code, locale_code)


def _render_prompt(context: dict[str, Any], extra_instructions: str) -> str:
    template = _load_prompt_template()
    claims_block = "\n".join(
        f"- {c['id']} | {c['verdict']} | {c['text']}" for c in context["claims"]
    ) or "(nenhum claim anexado)"
    return (
        template.replace("{opportunity_title}", context["opportunity_title"])
        .replace("{editorial_angle}", context["editorial_angle"])
        .replace("{key_message}", context["key_message"])
        .replace("{format}", context["format"] or "PHOTO_POST")
        .replace("{language_instruction}", context["language_instruction"])
        .replace("{extra_instructions}", extra_instructions or "(nenhuma)")
        .replace("{claims_block}", claims_block)
    )


def _validate_semantics(
    output: CopywriterOutput, context: dict[str, Any]
) -> None:
    """Deterministic gate: only attached, usable claims may be referenced."""
    allowed = {
        c["id"]: c for c in context["claims"] if c["verdict"] in USABLE_VERDICTS
    }
    if not output.claim_ids_used:
        raise CopywriterBlocked("draft uses no claims — cannot verify facts")
    for claim_id in output.claim_ids_used:
        if claim_id not in allowed:
            raise CopywriterBlocked(
                f"claim {claim_id} is not attached-and-usable; blocked"
            )
    if not output.title.strip() or not output.caption.strip():
        raise CopywriterBlocked("empty title or caption")
    for slide in output.slides:
        if not slide.text.strip():
            raise CopywriterBlocked(f"slide {slide.index} has empty text")


def write_draft(
    session: Session,
    ctx: ExecutionContext,
    package,
    provider,
    *,
    extra_instructions: str = "",
) -> tuple[CopywriterOutput, dict[str, Any]]:
    """Call the LLM through `provider`; return (validated proposal, provenance)."""
    context = build_context(session, ctx, package)
    prompt = _render_prompt(context, extra_instructions)
    try:
        result = provider.call(
            "llm.generate",
            {
                "prompt": prompt,
                "json_schema": COPYWRITER_JSON_SCHEMA,
                "temperature": 0.7,
            },
        )
    except ProviderUnavailable:
        raise  # transient — caller decides retry (Doc 03)
    except ProviderError as exc:
        raise CopywriterBlocked(f"provider content unusable: {exc}") from exc

    try:
        output = CopywriterOutput.model_validate(result.get("json"))
    except Exception as exc:  # pydantic ValidationError / wrong shape
        raise CopywriterBlocked(f"schema validation failed: {exc}") from exc

    _validate_semantics(output, context)
    return output, result


def metadata_from(result: dict[str, Any]) -> dict[str, Any]:
    """Provider/model provenance for the Draft payload (Doc 05 observability;
    never includes secrets)."""
    return {
        "prompt_version": PROMPT_VERSION,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "finish_reason": result.get("finish_reason"),
    }
