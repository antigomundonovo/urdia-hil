"""Provider OpenAI-compatível (Doc 17 §9/§15): serve a qualquer gateway que
exponha `/v1/chat/completions` (OmniRoute local, LiteLLM proxy, etc.).

Registrado como CANDIDATO — a troca do provider de produção exige benchmark
+ regression + aprovação humana (Doc 17 §9). Uso atual: benchmark via
`python -m scripts.benchmark_llm --gateway`.

A chave vive só em Settings (`.env`, nunca versionada/logada/repr — Doc 08).
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAICompatError(Exception):
    """Conteúdo inutilizável — falha fechada (não transitória)."""


class OpenAICompatUnavailable(Exception):
    """Indisponibilidade transitória (rede/429/5xx) — o caller decide retry."""


class OpenAICompatProvider:
    key = "openai-compat"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider_label: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if not base_url:
            raise OpenAICompatError("openai-compat: no base_url configured")
        if not api_key:
            raise OpenAICompatUnavailable("openai-compat: no API key configured")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self.key = provider_label or "openai-compat"
        self._timeout = timeout

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        if capability_key not in ("llm.generate",):
            raise OpenAICompatError(
                f"openai-compat does not implement capability {capability_key!r}"
            )
        prompt = str(payload.get("prompt", ""))
        if not prompt.strip():
            raise OpenAICompatError("openai-compat: empty prompt")

        messages: list[dict[str, str]] = []
        if payload.get("system"):
            messages.append({"role": "system", "content": str(payload["system"])})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": float(payload.get("temperature", 0.7)),
            "max_tokens": int(payload.get("max_output_tokens", 2048)),
        }
        # Modelos com raciocínio (ex.: gemini "thinking" via gateway) gastam
        # completion tokens pensado antes da resposta — teto maior evita
        # truncar o JSON (finish_reason=length).
        if body["max_tokens"] < 4096:
            body["max_tokens"] = 4096
        json_schema = payload.get("json_schema")
        if json_schema is not None:
            # json_schema estrito impõe o contrato (o json_object simples
            # permite campos extras — CopywriterOutput é extra="forbid").
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "urdia_output",
                    "schema": json_schema,
                    "strict": True,
                },
            }

        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise OpenAICompatUnavailable(
                f"openai-compat: timeout after {self._timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAICompatUnavailable(
                f"openai-compat: network error {exc.__class__.__name__}"
            ) from exc

        if response.status_code in (429,) or response.status_code >= 500:
            raise OpenAICompatUnavailable(
                f"openai-compat: HTTP {response.status_code}"
            )
        if response.status_code in (401, 403):
            raise OpenAICompatUnavailable(
                f"openai-compat: credential rejected ({response.status_code})"
            )
        if response.status_code != 200:
            raise OpenAICompatError(f"openai-compat: HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise OpenAICompatError("openai-compat: non-JSON response body") from exc

        choices = data.get("choices") or []
        if not choices:
            raise OpenAICompatError("openai-compat: empty choices")
        message = choices[0].get("message") or {}
        text = str(message.get("content", "")).strip()
        if not text:
            raise OpenAICompatError("openai-compat: empty completion")

        usage_raw = data.get("usage") or {}
        usage = {
            "input_tokens": int(usage_raw.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage_raw.get("completion_tokens", 0) or 0),
        }

        result: dict[str, Any] = {
            "text": text,
            "provider": self.key,
            "model": self._model,
            "finish_reason": choices[0].get("finish_reason"),
            "usage": usage,
        }
        if json_schema is not None:
            # Modelos podem embrulhar JSON em markdown fence — extrair
            # antes de validar (a validação de schema continua sendo o gate).
            candidate = text
            if candidate.startswith("```"):
                candidate = candidate.strip("`")
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:]
                candidate = candidate.strip()
            try:
                result["json"] = json.loads(candidate)
            except ValueError as exc:
                raise OpenAICompatError(
                    "openai-compat: completion is not valid JSON"
                ) from exc
        return result
