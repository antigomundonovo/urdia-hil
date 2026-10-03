"""Visual analyst (Doc 10): deterministic hashes + AI-proposed classification.

Absolute rule (Doc 10): visual similarity NEVER proves identity — hashes are
used for DUPLICATE detection and origin LEADS, nothing more. The AI
classification is a PROPOSAL recorded on the asset with provenance; it is
never a rights decision (Doc 11 gate stays dominant) and never blocks or
unblocks publication by itself.
"""

from __future__ import annotations

import base64

from packages.providers.gemini import ProviderError, ProviderUnavailable

# Doc 00 §16 / Doc 10 visual classes (packages.domain.enums.VisualClassification).
VISUAL_CLASSES = (
    "ORIGINAL_AS_RETRIEVED",
    "CROPPED",
    "RESTORED",
    "UPSCALED",
    "COLORIZED",
    "RECONSTRUCTED",
    "AI_GENERATED",
    "ILLUSTRATION",
    "UNKNOWN",
)

VISION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "visual_classification": {
            "type": "string",
            "enum": list(VISUAL_CLASSES),
        },
        "description": {"type": "string"},
        "confidence": {"type": "integer"},
    },
    "required": ["visual_classification"],
}

PROMPT = (
    "Você é o analista visual da URDIA (acervos históricos). Classifique a "
    "imagem em EXATAMENTE uma das categorias: ORIGINAL_AS_RETRIEVED (como "
    "recebida do acervo), CROPPED (recortada), RESTORED (restaurada), "
    "UPSCALED (ampliada), COLORIZED (colorizada), RECONSTRUCTED "
    "(reconstruída), AI_GENERATED (gerada por IA), ILLUSTRATION "
    "(ilustração/desenho), UNKNOWN (não é possível determinar). Responda no "
    "JSON do schema, com description curta (1-2 frases, pt-BR) e confidence "
    "0-100. Nunca afirme identidade de pessoas ou lugares: descreva apenas o "
    "que é visível."
)


class VisionBlocked(Exception):
    """Fail closed: unusable model output."""


def classify_image(provider, *, content: bytes, mime_type: str) -> dict:
    """Return the AI-proposed classification dict (validated); provider
    unavailability propagates so the caller can retry (Doc 03)."""
    payload = {
        "prompt": PROMPT,
        "images": [
            {
                "mime_type": mime_type,
                "data_base64": base64.b64encode(content).decode("ascii"),
            }
        ],
        "json_schema": VISION_JSON_SCHEMA,
        "temperature": 0.1,
    }
    try:
        result = provider.call("llm.vision", payload)
    except ProviderUnavailable:
        raise
    except ProviderError as exc:
        raise VisionBlocked(f"vision provider content unusable: {exc}") from exc

    data = result.get("json") or {}
    classification = str(data.get("visual_classification", ""))
    if classification not in VISUAL_CLASSES:
        raise VisionBlocked(f"invalid visual classification: {classification!r}")
    confidence = data.get("confidence")
    try:
        confidence = max(0, min(100, int(confidence))) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    description = str(data.get("description", "")).strip()
    return {
        "visual_classification": classification,
        "description": description,
        "confidence": confidence,
        "provider": result.get("provider"),
        "model": result.get("model"),
    }
