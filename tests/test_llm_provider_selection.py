"""Provider selection (Doc 17 §9): gateway de texto aprovado em 2026-10-04
vira produção; fallback Gemini quando o gateway não está configurado."""

from types import SimpleNamespace

from apps.worker import handlers_real


def test_text_provider_selects_gateway_when_configured(monkeypatch):
    monkeypatch.setattr(
        handlers_real,
        "_settings",
        lambda: SimpleNamespace(
            llm_provider="gateway",
            llm_gateway_base_url="http://localhost:20128/v1",
            llm_gateway_api_key="k",
            llm_gateway_model="auto/gemini",
            llm_gateway_label="gateway-omniroute",
        ),
    )
    provider = handlers_real._llm_text_provider()
    assert provider.key == "gateway-omniroute"
    assert provider._model == "auto/gemini"


def test_text_provider_falls_back_to_gemini_without_gateway(monkeypatch):
    monkeypatch.setattr(
        handlers_real,
        "_settings",
        lambda: SimpleNamespace(
            llm_provider="gateway",
            llm_gateway_base_url="",  # sem gateway configurado
            llm_gateway_api_key="",
            llm_gateway_model="auto/gemini",
            llm_gateway_label="gateway-omniroute",
        ),
    )
    provider = handlers_real._llm_text_provider()
    assert provider.key == "gemini"


def test_gemini_provider_selected_when_llm_provider_is_gemini(monkeypatch):
    monkeypatch.setattr(
        handlers_real,
        "_settings",
        lambda: SimpleNamespace(
            llm_provider="gemini",
            llm_gateway_base_url="http://localhost:20128/v1",
            llm_gateway_api_key="k",
            llm_gateway_model="auto/gemini",
            llm_gateway_label="gateway-omniroute",
        ),
    )
    assert handlers_real._llm_text_provider().key == "gemini"
