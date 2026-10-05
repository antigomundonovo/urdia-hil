"""OpenAI-compat provider (Doc 17 §9): mockado, sem rede. Prova o contrato
do adapter — erros fechados, transitórios classificados, usage mapeado."""

from types import SimpleNamespace

import pytest

from packages.providers import openai_compat as mod
from packages.providers.openai_compat import OpenAICompatProvider


def _response(status=200, body=None):
    return SimpleNamespace(status_code=status, json=lambda: body or {})


def _ok_body(content, finish="STOP", usage=None):
    data = {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
    }
    if usage:
        data["usage"] = usage
    return data


def _provider(**kw):
    return OpenAICompatProvider(
        base_url=kw.get("base_url", "http://gw.test/v1"),
        api_key=kw.get("api_key", "k"),
        model=kw.get("model", "m1"),
        provider_label=kw.get("provider_label"),
    )


def test_missing_key_fails_closed():
    with pytest.raises(mod.OpenAICompatUnavailable):
        OpenAICompatProvider(base_url="http://gw.test/v1", api_key="", model="m")


def test_empty_prompt_is_rejected():
    with pytest.raises(mod.OpenAICompatError):
        _provider().call("llm.generate", {"prompt": "  "})


def test_capability_whitelist():
    with pytest.raises(mod.OpenAICompatError):
        _provider().call("llm.vision", {"prompt": "x"})


def test_429_is_transient(monkeypatch):
    monkeypatch.setattr(mod.httpx, "post", lambda *a, **kw: _response(429, {}))
    with pytest.raises(mod.OpenAICompatUnavailable):
        _provider().call("llm.generate", {"prompt": "x"})


def test_400_is_fatal(monkeypatch):
    monkeypatch.setattr(mod.httpx, "post", lambda *a, **kw: _response(400, {}))
    with pytest.raises(mod.OpenAICompatError):
        _provider().call("llm.generate", {"prompt": "x"})


def test_json_result_is_parsed(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _response(
            200,
            _ok_body(
                '{"title": "T", "caption": "C"}',
                usage={"prompt_tokens": 5, "completion_tokens": 7},
            ),
        )

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    result = _provider().call(
        "llm.generate",
        {"prompt": "x", "json_schema": {"type": "object"}},
    )
    assert result["json"] == {"title": "T", "caption": "C"}
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 7}
    assert result["provider"] == "openai-compat"
    # json_schema pede response_format json_schema estrito
    rf = captured["json"]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] == {"type": "object"}


def test_markdown_fenced_json_is_extracted(monkeypatch):
    body = _ok_body('```json\n{"title": "T", "caption": "C"}\n```')
    monkeypatch.setattr(mod.httpx, "post", lambda *a, **kw: _response(200, body))
    result = _provider().call("llm.generate", {"prompt": "x", "json_schema": {}})
    assert result["json"] == {"title": "T", "caption": "C"}


def test_reasoning_models_get_headroom(monkeypatch):
    """max_output_tokens pequeno é elevado a 4096 — modelos que 'pensam'
    truncam o JSON caso contrário (finish_reason=length)."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _response(200, _ok_body('{"a": 1}'))

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    _provider().call("llm.generate", {"prompt": "x", "max_output_tokens": 100})
    assert captured["json"]["max_tokens"] == 4096
