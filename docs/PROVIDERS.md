# Provider Registry (Doc 17 §15)

> Regra (Doc 17 §9): não assumir provider único. Trocar exige benchmark +
> regression + approval. Este arquivo registra cada provider em uso:
> **provider, model, version, reason, benchmark, fallback**.

## LLM — `gemini` (Google AI Studio)

| Campo | Valor |
|---|---|
| Provider key | `gemini` (`packages/providers/gemini.py`) |
| Model | `gemini-2.5-flash` (configurável via `LLM_MODEL`) |
| Version/API | `generativelanguage.googleapis.com/v1beta`, `generateContent` |
| Capacidade | `llm.generate` (texto estruturado com `responseSchema`) |
| Registrado em | 2026-10-01 |
| Motivo | Primeiro provider LLM: desbloqueia Copywriter (Doc 05) e o handler `CONTENT_GENERATION`; chave fornecida pelo dono do projeto |
| Benchmark | **Pendente** — primeiro provider, sem concorrente para comparar; benchmark obligatório antes de qualquer troca |
| Regression | Suíte `tests/test_gemini_provider.py` (mockada) + gate semântico `tests/test_copywriter_agent.py` |
| Fallback | `FailingProvider` → handler falha fechado (`RetryableJobError`); sem provider alternativo de LLM registrado |
| Segurança | Chave só em Settings (`.env`, nunca versionada/logada/repr); saída do modelo é untrusted data e passa por schema + semantic gate (Doc 05/17 §10) |

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
