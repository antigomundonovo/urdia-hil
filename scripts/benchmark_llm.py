"""LLM provider benchmark CLI (Doc 17 §9/§15 — evidência obrigatória antes
de qualquer troca de provider; Doc 16 model regression).

Uso:
    python -m scripts.benchmark_llm            # baseline determinístico (sem rede, CI-safe)
    python -m scripts.benchmark_llm --live     # inclui chamada real ao Gemini (consome tokens)
    python -m scripts.benchmark_llm --live --throttle 30   # espaça chamadas (free tier)
    python -m scripts.benchmark_llm --gateway   # via gateway OpenAI-compat (OmniRoute local)

Grava JSON em artifacts/ e imprime resumo. Exit 1 se o baseline
determinístico falhar em qualquer gate (o harness em si está quebrado).
"""

import sys

sys.path.insert(0, ".")

from pathlib import Path  # noqa: E402

from agents.copywriter import COPYWRITER_JSON_SCHEMA  # noqa: E402
from packages.providers.gemini import GeminiProvider  # noqa: E402
from packages.providers.llm_bench import (  # noqa: E402
    DeterministicBaselineProvider,
    default_cases,
    run_benchmark,
    save_report,
)
from packages.shared.settings import get_settings  # noqa: E402

BASELINE = "deterministic-baseline"


def main() -> int:
    live = "--live" in sys.argv
    use_gateway = "--gateway" in sys.argv
    throttle = 0.0
    if "--throttle" in sys.argv:
        throttle = float(sys.argv[sys.argv.index("--throttle") + 1])
    cases = default_cases()

    settings = get_settings()
    has_key = bool(getattr(settings, "google_ai_api_key", None))
    gemini_adapter = GeminiProvider() if (has_key and live) else None

    gateway_adapter = None
    gateway_label = "gateway"
    if use_gateway:
        from packages.providers.openai_compat import OpenAICompatProvider

        s = get_settings()
        if s.llm_gateway_base_url and s.llm_gateway_api_key:
            gateway_adapter = OpenAICompatProvider(
                base_url=s.llm_gateway_base_url,
                api_key=s.llm_gateway_api_key,
                model=s.llm_gateway_model,
                provider_label=s.llm_gateway_label,
            )
            gateway_label = s.llm_gateway_label

    report = run_benchmark(
        [
            (BASELINE, DeterministicBaselineProvider),
            ("gemini", gemini_adapter),
            (gateway_label, gateway_adapter),
        ],
        cases,
        COPYWRITER_JSON_SCHEMA,
        case_delay_s=throttle,
    )

    print("LLM PROVIDER BENCHMARK (Doc 16 · Doc 17 §9/§15)")
    print(f"casos: {len(cases)} | gerado: {report.created_at}")
    for entry in report.providers:
        if entry["status"] == "skipped":
            print(f"  {entry['provider']}: SKIPPED ({entry['reason']})")
            continue
        summary = entry["summary"]
        print(
            f"  {entry['provider']}: ok={summary['ok']}/{summary['cases']} "
            f"qualidade={summary['mean_quality']} "
            f"latência_média={summary['mean_latency_s']}s "
            f"custo=US${summary['total_cost_usd']}"
        )
        for row in entry["cases"]:
            status = "OK " if row["ok"] else "ERR"
            detail = row["error"] or (
                f"schema={row['schema_ok']} sem={row['semantic_ok']} "
                f"slop={row['anti_slop_result']} "
                f"orig={row['originality_result']}"
            )
            print(f"    [{status}] {row['case_id']}: {detail}")

    baseline = next(
        e for e in report.providers if e["provider"] == BASELINE
    )
    if baseline["summary"]["ok"] != baseline["summary"]["cases"]:
        print("FALHA: o baseline determinístico deve passar em todos os gates")
        return 1

    out = save_report(report, Path("artifacts"))
    print(f"relatório: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
