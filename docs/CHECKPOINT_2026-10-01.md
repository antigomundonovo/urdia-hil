# Checkpoint Geral — 2026-10-01 (consolidado, pós LLM + plataformas)

**Branch:** `antigomundonovo-continuar-projeto` · **Repositório:** `antigomundonovo/urdia-hil`
**Caminho local:** `C:\urdia-hil` (único clone; antigos removidos)
**Estado:** ruff 100% limpo · **389 testes passando, 0 falhas** · local = GitHub (`db05de1`)
**CI:** roda em push/PR para `main` (testes + benchmarks + web). Trabalho diário validado localmente; pipeline formal via PR para main.

---

## 1. Milestones entregues (histórico consolidado)

| # | Marco | Commit | Resumo |
|---|---|---|---|
| M13 | Benchmarks Doc 16 | `afebd8a` | 140 casos (61 pytest + 79 script); rights gate fail-closed; SSRF; isolamento |
| M14 | Renderizador Doc 13 | `b68f2b3` | Pillow determinístico: PHOTO_POST + CAROUSEL (7 slides), QC, manifest `render` |
| M15 | Handlers JobEngine | `242697b` | 5 handlers reais (IMAGE_ANALYSIS, RIGHTS_RESEARCH, CLAIM_EXTRACTION, FORMAT_PLANNING, OPPORTUNITY_ANALYSIS) |
| M16 | Full review | `bac0487` | 2 bugs reais corrigidos (path duplicado no carousel; stubs no lugar de handlers reais); lint 100% |
| M17 | Worker 16/20 | `cb4df39` | QC, EXPORT, ANALYTICS_SYNC, COMMENT_SYNC, LEARNING_ANALYSIS reais |
| M18 | **LLM integrado** | `aafc32d` | GeminiProvider + agente Copywriter + CONTENT_GENERATION; prompt v1 versionado; gate semântico |
| M19 | Visão + fila | `d4718af` | IMAGE_ANALYSIS multimodal real (Doc 10) + `urdia-enqueue` CLI |
| — | Emenda 011 | `0ed8a7a` | Plataformas definitivas (7 redes; Kwai in; Pinterest/LinkedIn/Reddit out) |
| — | Capacidades + kit manual | `255a654` | Catálogo pesquisado (API vs MANUAL) + `MANUAL_POSTING.md` no export |
| — | Emenda 012: BRAIN + YouTube | `9aaf2ae` | Skills modulares + recipes determinísticas + YouTubeAdapter (yt-dlp) |
| — | Emenda 013: fronteira Studio/HIL + Social | `50ecda6..db05de1` | Contrato versionado; Factuality Challenge; Social Inbox (UHL-4); Audience Pulse/Demand (UHL-5); recovery de corrupção introduzida por ferramenta externa |

## 2. Estado do worker (fila de jobs)

**14/20 job types com handler real**; 6 stubs com justificativa de spec no
docstring (`apps/worker/handlers_new.py`):

- **Reais:** DISCOVERY_SCAN, SOURCE_RETRIEVAL*, CLAIM_VERIFICATION
  (`handlers.py` — produção) · IMAGE_ANALYSIS, RIGHTS_RESEARCH,
  CLAIM_EXTRACTION, FORMAT_PLANNING, OPPORTUNITY_ANALYSIS, QC, EXPORT,
  ANALYTICS_SYNC, COMMENT_SYNC, LEARNING_ANALYSIS, CONTENT_GENERATION
  (`handlers_real.py`) · *SOURCE_RETRIEVAL compartilha o handler do scan.
- **Stubs (por quê):** SOURCE_EXTRACTION/SOURCE_CLUSTERING (scan cobre),
  IMAGE_RESEARCH/ADVERSARIAL_RESEARCH (APIs de busca externas — lote humano),
  VISUAL_GENERATION (render roda no export), PUBLICATION (Emenda 007: manual-confirm).
- **Operação:** `urdia-enqueue --type X --workspace … --profile … [--payload '{…}']`
  · fail-closed sem ids (FatalJobError, sem retry) · provider indisponível → requeue.
- **LLM (Gemini):** `GOOGLE_AI_API_KEY` no `.env` (validada); modelo default
  `gemini-2.5-flash` (`LLM_MODEL`); registry em `docs/PROVIDERS.md` (benchmark
  pendente — obrigatório antes de trocar provider). Segurança: chave nunca em
  log/erro/repr (testado); saída do modelo = untrusted data → schema + gate
  semântico (só claims anexados com veredito POSSIBLE/PROBABLE/CONFIRMED).

## 2b. URDIA BRAIN (Emenda 012 — `docs/BRAIN.md`)

Executor determinístico de recipes sobre camada de skills com contrato:
**7 skills ativas** (research, factuality, scripting, image_inspection,
platform_policy, publication, analytics — todas delegando a handlers
existentes) + **3 declaradas** (visual_direction, seo, music — com motivo).
Recipes: `prepare_publication` (scripting opcional → gate → export PENDING),
`factuality_audit`, `research_sweep`. Human Gate intransponível; seleção de
skills por LLM só com benchmark + approval. YouTube virou fonte do discovery
(`yt-dlp`: metadados + legendas, nunca vídeo; cookies opcionais do operador:
`YTDLP_COOKIES_FROM_BROWSER`/`_FILE` — YouTube exige sessão p/ metadados).

## 2c. Camada social (Emenda 013 — contrato Studio/HIL)

HIL = Social/Audience Intelligence do ecossistema (contrato versionado em
`docs/CONTRATO_TECNOLOGICO_URDIA.md`). Novo módulo social:
- **FactualityChallenge** (§11): Comentário → challenge → research (fontes
  registradas) → judge determinístico → CONFIRMED/DISPUTED/UNSUPPORTED/UNKNOWN
  → **revisão humana** (gate). Comentário NUNCA é evidência por si.
- **Social Inbox** (UHL-4) e **Audience Pulse/Demand** (UHL-5) implementados
  por agente externo (OpenCode) durante o incidente; corrigidos/lintados e
  canônicos no alembic (head 7a6095fbc454).
- **Incidente 2026-10-02**: OpenCode commitou em paralelo (durante queda do
  Docker) e corrompeu a migração de pulso (bytes nulos). Recuperado: migração
  reescrita fielmente, tabelas órfãs recriadas via alembic, artefatos da
  ferramenta em quarentena (.gitignore; nada deletado, §12.12). RESOLVIDO
  (4f6f079): basetemp fixo removido do repo — pytest usa temp isolado fora
  do pytest-of; posicionamento do produto: **WEB-first** (README).
- API: `POST/GET /api/v1/social/challenges` (+ research/review/dismiss),
  `/social/inbox/*`, `/social/audience/demand|pulse`.

## 3. Plataformas (Emenda 011 + matriz 2026)

**Instagram · Facebook · X (Twitter) · YouTube · TikTok · Threads · Kwai**
(saiem do escopo: Pinterest, LinkedIn, Reddit).

| Rede | Método-alvo | Observação |
|---|---|---|
| Instagram/Facebook/Threads | API | Graph API; limites no catálogo |
| X | API | pay-per-use (~US$0,015/post; US$0,20 c/ link) |
| TikTok | API | Direct Post exige auditoria de app (senão sai privado) |
| YouTube | API (vídeo) | ~6 uploads/dia no quota default; Community posts → MANUAL |
| Kwai | MANUAL | sem API oficial (confirmado 2026-10-01) |

**Política do dono (implementada):** API → publica direto **após aprovação
humana** (Emenda 007); sem API → export gera `platform_variants/<rede>/MANUAL_POSTING.md`
completo (texto, mídias, hashtags, rastreabilidade, passos + rota de confirmação).
Catálogo: `packages/providers/platform_catalog.py` (descriptors declarados;
registry de adapters permanece vazio até credenciais + teste de revogação).
Detalhes/fontes: `docs/PLATFORM_CAPABILITIES.md`.

## 4. Correções recentes que valem lembrar

- Export do carousel gravava em `carousel/carousel/` (path duplicado) — corrigido.
- `build_handlers` registrava stubs para jobs com implementação real — corrigido.
- Mudança de PlatformPlan invalida QC (Doc 14) — comportamento confirmado em teste
  (re-rodar QC antes de exportar; approve persiste no audit).
- Formato das chaves do Google AI Studio mudou (`AQ.A…` ~53 chars, não mais
  `AIza…`) — validar contra a API real, nunca por formato (memória salva).

## 5. Documentação atualizada hoje

README (LLM opcional, worker/fila, redes) · RUNBOOK (seção urdia-enqueue) ·
`docs/PROVIDERS.md` (registro §15) · `docs/PLATFORM_CAPABILITIES.md` (matriz com
fontes) · HANDOFF 2026-09-30 marcado como superado (aponta para este checkpoint).

## 6. Próximos passos (sem intervenção humana)

1. ADVERSARIAL_RESEARCH assistido: propostas de contradição (IA) para revisão humana
   (pode virar skill `factuality` avançada).
2. Benchmarks dos providers LLM (pré-requisito para qualquer troca futura).
3. Testar YouTubeAdapter com cookies do operador (YouTube exige sessão).
4. PR/merge para `main` quando o dono quiser validar no CI.
5. Ajuste fino de recipes conforme uso real do Brain pelo dono.

## 7. Lote humano (atualizado 2026-10-02)

1. ~~Emendas 001–004~~ → **RESOLVIDO**: 001 SUPERADA (auth real já existe),
   003 APROVADA (nível 2 = teto V1), 004 APROVADA (DuckDB reservado);
   002 em aberto — dono pediu análise (anexo de encaixe no arquivo da emenda;
   decidir A/B/C quando puder).
2. **3–10 casos históricos reais** para benchmarks (fatos + fontes) — pendente.
3. Quando quiser publicação por API: credenciais por rede (app Meta Business,
   conta X dev com créditos, TikTok com auditoria, Google Cloud OAuth) — uma a uma.

> Nota: novas integrações de ferramentas serão analisadas caso a caso contra a
> constituição (Doc 17 Core Rule + §14/§15) — nada de Frankenstein: cada
> adição passa por spec → emenda se preciso → benchmark → testes.
