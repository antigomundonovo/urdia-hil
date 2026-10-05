# ROADMAP V2 — escopo reservado pelas emendas

> Fonte: Emendas 002, 004, 012 (o que ficou "para depois" e por quê).
> Regra: nada aqui pode violar a constituição (humano no publicação,
> fronteira Studio/HIL, juiz determinístico).

## Status

| Fase | Item | Origem | Estado |
|------|------|--------|--------|
| V2.1 | **Ponte Studio⇄HIL (OpenClaw)** — auth máquina-a-máquina + allowlist + export de demanda §10 | Emenda 002 Opção C | **EM ANDAMENTO** (2026-10-05): modelo `machine_clients`, migração `f1a2b3c4d5e6`, `apps/api/bridge_routes.py` (gestão de chaves por sessão humana + `GET /api/v1/bridge/demand` por chave de máquina), testes `tests/test_bridge.py` |
| V2.1a | Consumo do lado Studio: Studio lê `/bridge/demand` na cópia dele | contrato §10 | Pendente (requer cooperação da IA do Studio em `C:\Antigomundonovo`) |
| V2.2 | **Hermes** — memória auxiliar estruturada (Doc 05 §Memory) | Emenda 002 | **BASE ENTREGUE** (2026-10-05): modelo `agent_memories` (6 tipos, origem obrigatória p/ FACT fail-closed, supersede/archive append-only), `packages/research/memory.py`, API `/api/v1/memory`, testes. Uso real quando o Learning tiver dados |
| V2.3 | **MiroFish** — simulação de cenários editoriais | Emenda 002 | Reservado até ter dados reais |
| V2.4 | **DuckDB** — analítica offline read-only sobre metric_events/audit | Emenda 004 | **FERRAMENTA ENTREGUE** (2026-10-05): `packages/analytics/offline.py` (export read-only de tabelas append-only p/ snapshot DuckDB imutável) + `scripts/duckdb_export.py`; adoção rotineira quando o volume justificar |
| V2.5 | **Música** — declaração de direitos musicais (`music` → DECLARED) | Emenda 012 / Doc 13 | Fora do pipeline V1 |

## Regras da ponte (V2.1)

1. Chave de máquina (`urdia_mk_…`) é criada/revogada por humano logado e
   aparece em texto claro **uma única vez**; no banco só o digest SHA-256.
2. Allowlist = o próprio router `/api/v1/bridge`. Chave de máquina não
   autentica sessão nenhuma em outros routers (coberto por teste).
3. Export é **read-only**: demanda estruturada pronta para decisão humana
   do lado do Studio (contrato §10). Nada publica; nada assume.
4. Todo uso/cadastro/revogação gera `AuditEvent`.
5. Isolamento por workspace preservado: chave de um workspace nunca lê
   outro (404, sem existir confirmação).

## Pendências do dono (fora do código)

- Aprovação do TikTok (submetido 2026-10-04) → depois rotacionar
  `TIKTOK_PRODUCTION_CLIENT_SECRET`.
