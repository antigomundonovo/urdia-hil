"""Gemini LLM provider (Google AI Studio) — first LLM adapter (Doc 17 §9/§15).

Contract: same ProviderAdapter Protocol as every other provider; the registry
decides, not the caller. Registered as `gemini` / model from settings
(default gemini-3.8-flash) — see docs/PROVIDERS.md for the §15 registry entry
(model, version, reason, benchmark status, fallback).

Security (Doc 08/§12): the API key is read from Settings only, never logged,
never repr'd, never included in error messages. External content returned by
the model is untrusted data — callers must schema-validate (Doc 05 pipeline).

Fail-closed: no key → ProviderUnavailable; non-200 → ProviderUnavailable
(status only, no body echo); empty candidate → ProviderError; JSON schema
requested but unparseable → ProviderError.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from packages.providers.base import ProviderAdapter  # noqa: F401 — contract re-export

API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class ProviderUnavailable(Exception):
    """Transient: network, auth/config, quota, 5xx (Doc 03 retryable class)."""


class ProviderError(Exception):
    """Model returned unusable content (schema problem, empty candidate)."""


def _settings():
    from packages.shared.settings import get_settings

    return get_settings()


class GeminiProvider:
    key = "gemini"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        if api_key is None or model is None:
            settings = _settings()
            self._api_key = settings.google_ai_api_key if api_key is None else api_key
            self._model = model or settings.llm_model
        else:
            self._api_key = api_key
            self._model = model

    # --- ProviderAdapter ---------------------------------------------------

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        if capability_key not in ("llm.generate", "llm.vision"):
            raise ProviderError(f"gemini does not implement capability {capability_key!r}")
        return self.generate(
            prompt=str(payload.get("prompt", "")),
            system=payload.get("system"),
            json_schema=payload.get("json_schema"),
            temperature=float(payload.get("temperature", 0.7)),
            max_output_tokens=int(payload.get("max_output_tokens", 2048)),
            images=payload.get("images"),
        )

    # --- capability ---------------------------------------------------------

    def generate(
        self,
        *,
        prompt: str,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
        images: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ProviderUnavailable("gemini: no API key configured")
        if not prompt.strip():
            raise ProviderError("gemini: empty prompt")

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        }
        if json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = json_schema

        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image in images or []:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": str(image.get("mime_type", "image/png")),
                        "data": str(image.get("data_base64", "")),
                    }
                }
            )
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        from packages.shared.settings import get_settings

        timeout = get_settings().llm_timeout_seconds
        url = f"{API_BASE}/models/{self._model}:generateContent"
        try:
            response = httpx.post(
                url,
                params={"key": self._api_key},
                json=body,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"gemini: timeout after {timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"gemini: network error {exc.__class__.__name__}") from exc

        if response.status_code == 429:
            raise ProviderUnavailable("gemini: rate limited (429)")
        if response.status_code in (401, 403):
            raise ProviderUnavailable(f"gemini: credential rejected ({response.status_code})")
        if response.status_code != 200:
            raise ProviderUnavailable(f"gemini: HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("gemini: non-JSON response body") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("gemini: empty candidates")
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise ProviderError("gemini: empty completion")

        result: dict[str, Any] = {
            "text": text,
            "provider": self.key,
            "model": self._model,
            "finish_reason": candidates[0].get("finishReason"),
        }
        # Uso de tokens (Doc 17 §15 — benchmark de custo por provider).
        usage = data.get("usageMetadata")
        if usage:
            result["usage"] = {
                "input_tokens": int(usage.get("promptTokenCount", 0) or 0),
                "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
            }
        if json_schema is not None:
            try:
                result["json"] = json.loads(text)
            except ValueError as exc:
                raise ProviderError("gemini: completion is not valid JSON") from exc
        return result
