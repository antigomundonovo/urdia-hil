"""LLM benchmark harness (Doc 17 §9/§15): determinístico, sem rede.
Baseline sempre-verde prova o harness; providers falsos provam os gates.
"""

import json

import pytest

from agents.copywriter import COPYWRITER_JSON_SCHEMA
from packages.providers import gemini as gemini_module
from packages.providers.gemini import GeminiProvider
from packages.providers.llm_bench import (
    DeterministicBaselineProvider,
    default_cases,
    estimate_cost,
    grade,
    run_benchmark,
    run_case,
)


@pytest.fixture(scope="module")
def cases():
    return default_cases()


def _provider_from(payload, *, usage=None, provider="fake", model="fake-1"):
    class _Fake:
        def __init__(self):
            self.key = provider
            self.model = model

        def call(self, capability_key, payload_dict):
            out = {
                "provider": self.key,
                "model": self.model,
                "finish_reason": "STOP",
            }
            if usage is not None:
                out["usage"] = usage
            out["json"] = json.loads(json.dumps(payload))
            return out

    return _Fake()


def test_baseline_passes_all_gates(cases):
    report = run_benchmark(
        [("deterministic-baseline", DeterministicBaselineProvider)],
        cases,
        COPYWRITER_JSON_SCHEMA,
    )
    summary = report.providers[0]["summary"]
    assert summary["ok"] == summary["cases"]
    assert summary["mean_quality"] == 1.0


def test_skipped_provider_is_recorded_not_simulated(cases):
    report = run_benchmark([("gemini", None)], cases, COPYWRITER_JSON_SCHEMA)
    entry = report.providers[0]
    assert entry["status"] == "skipped"
    assert "cases" not in entry


def test_cost_estimation_uses_pricing_table():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert (
        estimate_cost("gemini", "gemini-2.5-flash", usage) == pytest.approx(2.80)
    )
    # Provider/modelo sem preço confirmado na tabela: None (nunca inventado).
    assert estimate_cost("openai", "gpt-x", usage) is None
    assert (
        estimate_cost("gemini", "gemini-3.8-flash", usage) is None
    )
    assert estimate_cost("gemini", "gemini-2.5-flash", None) == 0.0


def test_provider_error_is_recorded(cases):
    class _Broken:
        key = "broken"
        model = "n/a"

        def call(self, capability_key, payload):
            raise RuntimeError("network down")

    outcome = run_case(_Broken(), cases[0], COPYWRITER_JSON_SCHEMA)
    assert outcome.ok is False
    assert "RuntimeError" in (outcome.error or "")
    assert outcome.latency_s >= 0.0


def test_schema_violation_is_flagged(cases):
    bad = {"title": 123, "caption": None}  # tipos errados de propósito
    provider = _provider_from(bad)
    result = provider.call("llm.generate", {})
    outcome = grade(cases[0], result, 0.1)
    assert outcome.schema_ok is False
    assert outcome.ok is False
    assert "schema validation failed" in (outcome.error or "")


def test_controversy_claim_blocks_semantic_gate(cases):
    """Usar a crença popular (veredito UNKNOWN) deve derrubar o gate
    determinístico — núcleo da regra 'afirme pouco' (Doc 16)."""
    controversy = next(c for c in cases if any("BELIEF" in cl["id"] for cl in c.claims))
    belief_id = next(cl["id"] for cl in controversy.claims if cl["verdict"] == "UNKNOWN")
    payload = {
        "title": "Título",
        "caption": "Legenda",
        "claim_ids_used": [belief_id],
        "slides": [],
        "seo": {"entities": [], "keywords": []},
    }
    provider = _provider_from(payload)
    result = provider.call("llm.generate", {})
    outcome = grade(controversy, result, 0.1)
    assert outcome.schema_ok is True
    assert outcome.semantic_ok is False
    assert "not attached-and-usable" in (outcome.error or "")


def test_usage_flows_into_cost(cases):
    usable = [cl for cl in cases[0].claims if cl["verdict"] == "PROBABLE"]
    payload = {
        "title": "Título",
        "caption": "Legenda",
        "claim_ids_used": [cl["id"] for cl in usable],
        "slides": [],
        "seo": {"entities": [], "keywords": []},
    }
    provider = _provider_from(
        payload,
        usage={"input_tokens": 100_000, "output_tokens": 10_000},
        provider="gemini",
        model="gemini-2.5-flash",
    )
    result = provider.call("llm.generate", {})
    outcome = grade(cases[0], result, 0.5)
    assert outcome.input_tokens == 100_000
    # 100k in × $0.30/1M + 10k out × $2.50/1M = 0.03 + 0.025
    assert outcome.cost_usd == pytest.approx(0.055, abs=1e-6)
    assert outcome.latency_s == pytest.approx(0.5)
    assert outcome.ok is True


def test_gemini_usage_metadata_is_surfaced(monkeypatch):
    body = {
        "candidates": [
            {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7},
    }
    monkeypatch.setattr(
        gemini_module.httpx,
        "post",
        lambda *a, **kw: type(
            "R", (), {"status_code": 200, "json": staticmethod(lambda: body)}
        )(),
    )
    result = GeminiProvider(api_key="k", model="m").generate(prompt="teste")
    assert result["usage"] == {"input_tokens": 11, "output_tokens": 7}
