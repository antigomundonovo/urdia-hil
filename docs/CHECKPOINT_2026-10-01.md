# Checkpoint Geral — 2026-10-01 (pós-review completo)

**Branch:** `antigomundonovo-continuar-projeto`
**Repositório:** `antigomundonovo/urdia-hil`
**Estado:** ruff 100% limpo · **311 testes passando, 0 falhas** · local = GitHub

---

## 1. Review completo executado nesta sessão

### Correções de qualidade (lint)
- `packages/rendering/engine.py` — 3 linhas >100 chars reformatadas (chamadas `_draw_text_block` quebradas em argumentos múltiplos).
- `packages/rendering/qc.py` — assinatura de `render_metadata_block` quebrada em múltiplas linhas.
- `packages/research/content.py` — lista de subpastas do export reformatada; `zip(specs, CAROUSEL_SLIDES, strict=True)` adicionado (B905: contrato explícito de 7 slides); caminho do slide unificado em `path`.
- `tests/test_job_handlers.py` — reescrito: import no topo (E402), registro cobre todos os JobTypes, stubs OK com payload vazio, reais fail-closed sem ids.
- `tests/test_job_handlers_real.py` — linha >100 corrigida;`DummySession` restaura `add()` usado pelo `append_audit`.
- `apps/worker/handlers_real.py` — variáveis não usadas removidas (`service`, `rights_service`, `knowledge`), imports órfãos removidos (`PhotoService`, `RightsService`, `KnowledgeService`, `_get_settings`), linhas longas reformatadas.

### Bugs reais encontrados e corrigidos
1. **Path duplicado no export do carousel** (`carousel/carousel/slide-01-...png`): a linha de escrita somava `"carousel"` duas vezes — render falhava com 409 no export CAROUSEL. Corrigido para `export_dir / path`.
2. **Worker registrava stubs no lugar de handlers reais**: `build_handlers()` mapeava `DISCOVERY_SCAN`, `SOURCE_RETRIEVAL` e `CLAIM_VERIFICATION` para no-ops, enquanto as implementações de produção existiam em `apps/worker/handlers.py` (só usadas por testes). Corrigido: produção usa os handlers reais.
3. **`DummySession` sem `add()`** fazia `append_audit` quebrar nos testes do JobEngine — restaurado.

### Limpeza / dependências
- `handlers_new.py` enxuto: apenas os 12 stubs restantes (os 3 duplicados com handlers reais foram removidos).
- Verificação de dependências do `pyproject.toml`: nenhuma a remover. Uvicorn (servidor), Alembic (migrations CLI), psycopg (driver Postgres) e pgvector (extensão vetorial Doc 05) são infraestrutura sem import direto — todos necessários.
- Nenhum arquivo órfão rastreado; caches (`.pytest_cache`, `.ruff_cache`, `__pycache__`, `urdia_hil.egg-info`) não são versionados.

---

## 2. Registro de handlers (estado final)

| JobType | Implementação |
|---|---|
| DISCOVERY_SCAN / SOURCE_RETRIEVAL | `handlers.py` (real: DiscoveryEngine + SafeFetcher) |
| CLAIM_VERIFICATION | `handlers.py` (real: vereditos determinísticos Doc 16) |
| IMAGE_ANALYSIS | `handlers_real.py` (valida payload; análise plena pende do wiring de analyzers) |
| RIGHTS_RESEARCH | `handlers_real.py` (nunca degrada para public domain — Doc 11) |
| CLAIM_EXTRACTION | `handlers_real.py` (extração plena pende do parser de conteúdo) |
| FORMAT_PLANNING | `handlers_real.py` (conjunto fechado V1 — Emenda 006) |
| OPPORTUNITY_ANALYSIS | `handlers_real.py` (opportunity_ids opcional) |
| 12 restantes (SOURCE_EXTRACTION, SOURCE_CLUSTERING, IMAGE_RESEARCH, ADVERSARIAL_RESEARCH, CONTENT_GENERATION, VISUAL_GENERATION, QC, EXPORT, PUBLICATION, ANALYTICS_SYNC, COMMENT_SYNC, LEARNING_ANALYSIS) | stubs no-op em `handlers_new.py` |

Fail-closed garantido: payload sem os ids obrigatórios → `FatalJobError` → job FAILED, sem retry (Doc 03).

---

## 3. Milestones já consolidados (histórico)

- **M13** — Benchmarks Doc 16: 140 casos (61 pytest + 79 scripts/benchmark.py).
- **M14** — Renderizador determinístico Doc 13 (PHOTO_POST + CAROUSEL, QC, manifest com `render` block).
- **M15** — Handlers reais do JobEngine para 5 JobTypes + cobertura de registro.

---

## 4. Próximos passos (sem intervenção humana)

1. Substituir stubs restantes por implementações reais conforme a ordem do Doc 17.
2. Completar IMAGE_ANALYSIS com o pass de perceptual-hash/dedupe (analyzers já existem).
3. Runbook do worker (Docker/K8s) em `docs/RUNBOOK.md`.

## 5. Lote humano (acumulado para o final — instrução do usuário)

1. Chaves LLM (Google AI Studio) — desbloqueia agentes de geração.
2. 3–10 casos históricos reais para benchmarks.
3. Decisões de emendas pendentes (001–004 pré-definidas).
