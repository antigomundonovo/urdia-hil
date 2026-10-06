"""LLM provider benchmark harness (Doc 17 §9/§15, Doc 16 model regression).

Troca de provider LLM exige benchmark + regression + compare + approve +
promote. Este harness gera a EVIDÊNCIA de benchmark: roda casos fixos
(dataset canônico do dono, Doc 16) por provider e mede latência, tokens,
custo e qualidade com os MESMOS gates determinísticos da produção (schema
CopywriterOutput, semantic gate de claims, anti-slop, originalidade).

Veredito nunca é opinião do agente (Doc 17 §4): tudo no relatório é
checagem determinística ou medida bruta (tempo/tokens). Providers sem
credencial são reportados como `skipped` — nunca simulados.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.contracts.agents import CopywriterOutput
from packages.research.analyzers import check_anti_slop, check_originality

DATASET_PATH = Path("assets/datasets/historical_facts.json")

# Custo USD por 1M tokens (input/output) — tabela pública; `as_of` é
# obrigatório e a confirmação na hora da troca é passo do checklist (§15).
# Preço None = não confirmado nesta data → custo reportado como None
# (nunca inventado); preencher com a tabela oficial antes de uma troca.
PRICING: dict[str, dict[str, Any]] = {
    "gemini/gemini-3.8-flash": {
        "input_per_1m": None,
        "output_per_1m": None,
        "as_of": "2026-10 (confirmar na troca)",
    },
    # Descontinuado pela API para chaves novas (mensagem oficial, 2026-10).
    "gemini/gemini-2.5-flash": {
        "input_per_1m": 0.30,
        "output_per_1m": 2.50,
        "as_of": "2025-10 (modelo descontinuado p/ chaves novas em 2026-10)",
        "deprecated": True,
    },
}


@dataclass
class BenchCase:
    """Caso de benchmark no formato de contexto do copywriter (Doc 05)."""

    id: str
    opportunity_title: str
    editorial_angle: str
    key_message: str
    claims: list[dict[str, str]]  # {id, verdict, text}
    sources: list[tuple[str, str]]  # (reference, text) p/ originalidade

    def context(self) -> dict[str, Any]:
        from packages.domain.profile_defaults import DEFAULT_EDITORIAL_POLICY
        from packages.multilingual import describe_pair

        # O corpus de benchmark é o dataset histórico em português —
        # idioma EXPLÍTITO do contrato (Emenda 014), não dedução.
        language_instruction = describe_pair(
            DEFAULT_EDITORIAL_POLICY["language_code"],
            DEFAULT_EDITORIAL_POLICY["locale_code"],
        )
        return {
            "opportunity_title": self.opportunity_title,
            "editorial_angle": self.editorial_angle,
            "key_message": self.key_message,
            "format": "PHOTO_POST",
            "claims": self.claims,
            "language_instruction": language_instruction,
        }


@dataclass
class CaseOutcome:
    case_id: str
    provider: str
    model: str
    ok: bool
    error: str | None = None
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0  # None = preço não confirmado na tabela
    schema_ok: bool = False
    semantic_ok: bool = False
    anti_slop_result: str | None = None
    originality_result: str | None = None
    quality_score: float = 0.0  # 0..1 — média dos gates determinísticos


@dataclass
class BenchmarkReport:
    created_at: str
    providers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "schema_version": 1,
            "providers": self.providers,
        }


def default_cases(dataset_path: Path = DATASET_PATH) -> list[BenchCase]:
    """Casos canônicos derivados do dataset do dono (um por fato). No caso
    de controvérsia, a crença popular CONTRÁRIA ao fato real entra como
    claim UNKNOWN — o gate determinístico deve bloquear quem a usar."""
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = data["cases"]
    by_id = {c["id"]: c for c in cases}
    assert "H1" in by_id, "dataset canônico sem H1"

    controversy = next((c for c in cases if "popular_belief" in c), None)

    out: list[BenchCase] = []
    for src in cases:
        claims: list[dict[str, str]] = [
            {
                "id": str(src["id"]),
                "verdict": "PROBABLE",
                "text": str(src["statement"]),
            }
        ]
        if controversy is not None and src["id"] == controversy["id"]:
            claims.append(
                {
                    "id": f"{src['id']}-BELIEF",
                    "verdict": "UNKNOWN",
                    "text": str(controversy["popular_belief"]),
                }
            )
        out.append(
            BenchCase(
                id=f"BENCH-{src['id']}",
                opportunity_title=str(src["statement"])[:80],
                editorial_angle="História real, checada, com fonte primária",
                key_message=str(src["statement"])[:140],
                claims=claims,
                sources=[
                    (str(src["source_name"]), str(src["statement"])),
                ],
            )
        )
    return out


def estimate_cost(
    provider: str, model: str, usage: dict[str, Any] | None
) -> float | None:
    """Custo estimado a partir da tabela; None = preço não confirmado."""
    if not usage:
        return 0.0
    entry = PRICING.get(f"{provider}/{model}")
    if entry is None:
        return None
    input_price, output_price = entry["input_per_1m"], entry["output_per_1m"]
    if input_price is None or output_price is None:
        return None
    cost = (
        int(usage.get("input_tokens", 0)) / 1_000_000 * input_price
        + int(usage.get("output_tokens", 0)) / 1_000_000 * output_price
    )
    return round(cost, 6)


def grade(case: BenchCase, result: dict[str, Any], latency_s: float) -> CaseOutcome:
    """Gates determinísticos (mesmos da produção) sobre um resultado."""
    provider = str(result.get("provider", "unknown"))
    model = str(result.get("model", "unknown"))
    usage = result.get("usage") or {}
    outcome = CaseOutcome(
        case_id=case.id,
        provider=provider,
        model=model,
        ok=False,
        latency_s=round(latency_s, 4),
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cost_usd=estimate_cost(provider, model, usage),
    )
    payload = result.get("json")
    if not isinstance(payload, dict):
        outcome.error = "provider returned no structured json"
        return outcome
    try:
        output = CopywriterOutput.model_validate(payload)
    except Exception as exc:
        outcome.error = f"schema validation failed: {exc}"
        return outcome
    outcome.schema_ok = True

    from agents.copywriter import _validate_semantics

    try:
        _validate_semantics(output, case.context())
        outcome.semantic_ok = True
    except Exception as exc:
        outcome.error = f"semantic gate: {exc}"

    slop = check_anti_slop(output.title, output.caption)
    outcome.anti_slop_result = slop.result
    originality = check_originality(
        f"{output.title}\n{output.caption}", case.sources
    )
    outcome.originality_result = originality.result

    gates = [
        outcome.schema_ok,
        outcome.semantic_ok,
        slop.result != "FAIL",
        originality.result != "FAIL",
    ]
    outcome.quality_score = round(sum(gates) / len(gates), 3)
    outcome.ok = outcome.quality_score == 1.0 and outcome.error is None
    return outcome


def run_case(
    provider: Any,
    case: BenchCase,
    json_schema: dict[str, Any],
    *,
    attempts: int = 4,
) -> CaseOutcome:
    """Usa o MESMO template de prompt da produção (com claims block — sem
    ele o modelo não conhece os IDs anexados) e re-tenta erros transitórios
    (ProviderUnavailable: 429/503) com backoff crescente."""
    from agents.copywriter import _render_prompt

    prompt = _render_prompt(case.context(), "")
    started = time.perf_counter()
    last_error: str | None = None
    backoff = [5.0, 15.0, 30.0]
    for attempt in range(attempts):
        try:
            result = provider.call(
                "llm.generate",
                {
                    "prompt": prompt,
                    "json_schema": json_schema,
                    "temperature": 0.7,
                },
            )
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            transient = exc.__class__.__name__ == "ProviderUnavailable"
            if transient and attempt < attempts - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return CaseOutcome(
                case_id=case.id,
                provider=str(getattr(provider, "key", "unknown")),
                model=str(getattr(provider, "model", "n/a")),
                ok=False,
                error=last_error,
                latency_s=round(time.perf_counter() - started, 4),
            )
        return grade(case, dict(result), time.perf_counter() - started)
    raise AssertionError("unreachable: attempts loop must return")


class DeterministicBaselineProvider:
    """Baseline SEMPRE-VERDE, sem rede e sem custo: devolve a saída válida
    derivada do próprio caso (somente claims usable). NÃO é um LLM — existe
    para CI e para exercitar os gates; não compara qualidade editorial."""

    key = "deterministic-baseline"
    model = "rule-based-v1"

    def __init__(self, case: BenchCase) -> None:
        usable = [
            c
            for c in case.claims
            if c["verdict"] in {"POSSIBLE", "PROBABLE", "CONFIRMED"}
        ]
        # Texto transformado (não copia o statement da fonte — o gate de
        # originalidade reprova near-copy; Doc 16).
        source_name = case.sources[0][0]
        self._payload: dict[str, Any] = {
            "title": f"Você sabia? {source_name}",
            "caption": (
                f"Contexto completo na fonte: {source_name}. "
                "Fatos checados antes de publicar."
            ),
            "claim_ids_used": [c["id"] for c in usable],
            "slides": [],
            "seo": {"entities": [], "keywords": []},
        }

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        del capability_key, payload
        return {
            "provider": self.key,
            "model": self.model,
            "finish_reason": "STOP",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "json": dict(self._payload),
        }


def run_benchmark(
    providers: list[tuple[str, Any]],
    cases: list[BenchCase],
    json_schema: dict[str, Any],
    *,
    case_delay_s: float = 0.0,
) -> BenchmarkReport:
    """providers: lista de (nome_no_relatório, adapter_ou_None). `None`
    significa "sem credencial — skipped", nunca simulado. `case_delay_s`
    espaça chamadas live (quota por minuto do free tier)."""
    report = BenchmarkReport(
        created_at=datetime.now(UTC).isoformat(timespec="seconds")
    )
    for name, adapter in providers:
        if adapter is None:
            report.providers.append(
                {"provider": name, "status": "skipped", "reason": "no credential"}
            )
            continue
        if isinstance(adapter, type):
            # Fábrica de baseline: uma instância por caso (a saída do
            # baseline deriva do próprio caso).
            adapters = {case.id: adapter(case) for case in cases}
            outcomes = [
                run_case(adapters[case.id], case, json_schema) for case in cases
            ]
        else:
            outcomes: list[CaseOutcome] = []
            for index, case in enumerate(cases):
                if case_delay_s and index > 0:
                    time.sleep(case_delay_s)
                outcomes.append(run_case(adapter, case, json_schema))
        latencies = [o.latency_s for o in outcomes]
        report.providers.append(
            {
                "provider": name,
                "status": "ran",
                "cases": [asdict(o) for o in outcomes],
                "summary": {
                    "cases": len(outcomes),
                    "ok": sum(1 for o in outcomes if o.ok),
                    "failed": sum(1 for o in outcomes if not o.ok),
                    "mean_quality": round(
                        statistics.fmean([o.quality_score for o in outcomes]), 3
                    ),
                    "mean_latency_s": round(statistics.fmean(latencies), 4),
                    "total_cost_usd": (
                        None
                        if any(o.cost_usd is None for o in outcomes)
                        else round(sum(o.cost_usd for o in outcomes), 6)
                    ),
                },
            }
        )
    return report


def save_report(report: BenchmarkReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"llm-benchmark-{stamp}.json"
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
