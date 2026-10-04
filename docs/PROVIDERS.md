# Provider Registry (Doc 17 §15)

> Regra (Doc 17 §9): não assumir provider único. Trocar exige benchmark +
> regression + approval. Este arquivo registra cada provider em uso:
> **provider, model, version, reason, benchmark, fallback**.

## LLM — `gemini` (Google AI Studio)

| Campo | Valor |
|---|---|
| Provider key | `gemini` (`packages/providers/gemini.py`) |
| Model | `gemini-3.8-flash` (configurável via `LLM_MODEL`). **2026-10-04**: `gemini-2.5-flash` foi descontinuado pela API para chaves novas (HTTP 404 com mensagem oficial) — migração forçada, não escolha; validado ao vivo com a chave do projeto |
| Version/API | `generativelanguage.googleapis.com/v1beta`, `generateContent` |
| Capacidade | `llm.generate` (texto estruturado com `responseSchema`) |
| Registrado em | 2026-10-01 (model migrado em 2026-10-04) |
| Motivo | Primeiro provider LLM: desbloqueia Copywriter (Doc 05) e o handler `CONTENT_GENERATION`; chave fornecida pelo dono do projeto |
| Benchmark | **Harness entregue 2026-10-04** (`packages/providers/llm_bench.py` + `python -m scripts.benchmark_llm`): casos do dataset canônico, gates determinísticos de produção (schema + semantic gate + anti-slop + originalidade), latência/tokens/custo. Evidência: 2 casos ao vivo 100% dos gates (artifacts/llm-benchmark-20261004-184937.json); rodada completa pendente por **429/503 persistente do free tier** do 3.8-flash (re-tentar em janela de quota ou com tier pago). Preço do 3.8-flash: NÃO confirmado (custo reportado como `None` — nunca inventado) |
| Regression | Suíte `tests/test_gemini_provider.py` (mockada) + gate semântico `tests/test_copywriter_agent.py` + `tests/test_llm_bench.py` (harness determinístico, baseline sempre-verde) |
| Fallback | `FailingProvider` → handler falha fechado (`RetryableJobError`); sem provider alternativo de LLM registrado |
| Segurança | Chave só em Settings (`.env`, nunca versionada/logada/repr); saída do modelo é untrusted data e passa por schema + semantic gate (Doc 05/17 §10) |

## LLM — `gateway-omniroute` (CANDIDATO — aguarda aprovação humana p/ produção)

| Campo | Valor |
|---|---|
| Provider key | `openai-compat` com label `gateway-omniroute` (`packages/providers/openai_compat.py`) |
| Model | `auto/gemini` via OmniRoute local (`http://localhost:20128/v1`, roteamento sobre as contas do dono) |
| Version/API | OpenAI-compatible `/v1/chat/completions`, `response_format: json_schema` (strict) |
| Capacidade | `llm.generate` (JSON estruturado; campos extras bloqueados pelo schema + gate) |
| Registrado em | 2026-10-04 (CANDIDATO — benchmark concluído, aprovação pendente) |
| Motivo | Contornar o 429/503 persistente do free tier do Google AI Studio usando o gateway já instalado pelo dono |
| Benchmark | **APROVADO 2026-10-04**: 7/7 casos ao vivo, 100% dos gates determinísticos (schema + semantic + anti-slop + originalidade), latência média 12,9s (artifacts/llm-benchmark-20261004-193716.json). Comparação: `gemini` direto ficou em 2/7 no mesmo dia por 429 do free tier |
| Regression | `tests/test_openai_compat.py` (8 testes mockados) + `tests/test_llm_bench.py`; gate semântico de produção intacto |
| Fallback | `FailingProvider` → handler falha fechado; gateway depende do PC do dono estar ligado com o OmniRoute rodando |
| Segurança | Chave do gateway só em Settings/`.env` (nunca versionada/logada/repr); saída do modelo é untrusted data e passa por schema + semantic gate |
| Observações | Custo NÃO confirmado (as contas por trás do gateway variam — reportado como `None`). Rodar o OmniRoute localmente só funciona na máquina do dono: CI (GitHub Actions) mantém o baseline determinístico. Para produção, requer decisão do dono (Doc 17 §9, automation_level 2) |

## Regras de troca (checklist)

1. Benchmark do novo provider vs atual (qualidade + custo + latência).
2. Suíte de regression verde com o novo provider.
3. Registro atualizado nesta tabela (model, version, reason, benchmark, fallback).
4. Aprovação humana (automation_level 2).

## Providers não-LLM já registrados no código

| Provider | Arquivo | Papel |
|---|---|---|
| `laya` / `laya_shadow` | `packages/providers/laya*.py` | Avaliador shadow consultivo (AMENDMENT-010: sem autoridade editorial) |
| plataformas (V2) | `packages/providers/platforms.py` | Registry provider-neutral; nenhum adapter habilitado por padrão |
| `failing` / `echo` | `packages/providers/base.py` | Testes/dev: exercitar fallback e stub determinístico |
