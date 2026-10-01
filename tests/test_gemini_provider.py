"""GeminiProvider unit tests — all network interactions are mocked.

These tests never use the real API key and never hit the network (Doc 17:
tests must be deterministic). One optional live test skips itself when no
key is configured — it only lists models (zero generation cost).
"""

import httpx
import pytest

from packages.providers import gemini as gemini_module
from packages.providers.gemini import GeminiProvider, ProviderError, ProviderUnavailable


def _response(status_code: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=body or {})


def _ok_body(text: str = "olá") -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ]
    }


def test_missing_key_fails_closed():
    provider = GeminiProvider(api_key="", model="gemini-2.5-flash")
    with pytest.raises(ProviderUnavailable):
        provider.generate(prompt="teste")


def test_empty_prompt_is_rejected():
    provider = GeminiProvider(api_key="k", model="gemini-2.5-flash")
    with pytest.raises(ProviderError):
        provider.generate(prompt="   ")


def test_http_500_is_transient(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    monkeypatch.setattr(
        gemini_module.httpx, "post", lambda *a, **kw: _response(500)
    )
    with pytest.raises(ProviderUnavailable):
        provider.generate(prompt="teste")


def test_rate_limit_is_transient(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    monkeypatch.setattr(
        gemini_module.httpx, "post", lambda *a, **kw: _response(429)
    )
    with pytest.raises(ProviderUnavailable, match="429"):
        provider.generate(prompt="teste")


def test_bad_credentials_are_transient(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    monkeypatch.setattr(
        gemini_module.httpx, "post", lambda *a, **kw: _response(403)
    )
    with pytest.raises(ProviderUnavailable, match="403"):
        provider.generate(prompt="teste")


def test_timeout_is_transient(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")

    def raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(gemini_module.httpx, "post", raise_timeout)
    with pytest.raises(ProviderUnavailable, match="timeout"):
        provider.generate(prompt="teste")


def test_successful_completion(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    monkeypatch.setattr(
        gemini_module.httpx,
        "post",
        lambda *a, **kw: _response(200, _ok_body("texto gerado")),
    )
    result = provider.generate(prompt="teste")
    assert result["text"] == "texto gerado"
    assert result["provider"] == "gemini"
    assert result["model"] == "m"
    assert "json" not in result


def test_json_schema_result_is_parsed(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    body = _ok_body('{"title": "T", "caption": "C"}')
    monkeypatch.setattr(
        gemini_module.httpx, "post", lambda *a, **kw: _response(200, body)
    )
    result = provider.generate(prompt="teste", json_schema={"type": "object"})
    assert result["json"] == {"title": "T", "caption": "C"}


def test_invalid_json_with_schema_is_fatal(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    body = _ok_body("isto não é json")
    monkeypatch.setattr(
        gemini_module.httpx, "post", lambda *a, **kw: _response(200, body)
    )
    with pytest.raises(ProviderError, match="not valid JSON"):
        provider.generate(prompt="teste", json_schema={"type": "object"})


def test_empty_candidates_is_fatal(monkeypatch):
    provider = GeminiProvider(api_key="k", model="m")
    monkeypatch.setattr(
        gemini_module.httpx, "post", lambda *a, **kw: _response(200, {"candidates": []})
    )
    with pytest.raises(ProviderError, match="empty candidates"):
        provider.generate(prompt="teste")


def test_unknown_capability_is_rejected():
    provider = GeminiProvider(api_key="k", model="m")
    with pytest.raises(ProviderError, match="capability"):
        provider.call("other.capability", {})


def test_error_messages_never_contain_the_key():
    """Doc 08: secrets never appear in logs/errors — sanity-check the
    exception paths carry only statuses/generic messages."""
    provider = GeminiProvider(api_key="SEGREDO-ULTRA-SECRETO", model="m")
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            gemini_module.httpx, "post", lambda *a, **kw: _response(403)
        )
        with pytest.raises(ProviderUnavailable) as exc_info:
            provider.generate(prompt="teste")
    finally:
        monkeypatch.undo()
    assert "SEGREDO-ULTRA-SECRETO" not in str(exc_info.value)


def _live_key_configured() -> bool:
    from packages.shared.settings import get_settings

    return bool(get_settings().google_ai_api_key)


@pytest.mark.skipif(not _live_key_configured(), reason="live key not configured")
def test_live_key_lists_models():
    """Zero-cost credential check: only the models list, no generation."""
    provider = GeminiProvider()
    response = httpx.get(
        f"{gemini_module.API_BASE}/models", params={"key": provider._api_key}
    )
    assert response.status_code == 200
