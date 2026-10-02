# URDIA BRAIN — orquestrador modular de skills (AMENDMENT-012)

> **Nada aqui é um "LLM gigante que faz tudo".** O Brain é um executor
> determinístico de recipes: ele SELECIONA skills declaradas em código
> revisado. O LLM entra apenas onde já tem gate (Copywriter, visão).

## Arquitetura

```text
URDIA BRAIN (executor determinístico de recipes)
│
├── Planner            → Recipe declarada em código (sem LLM na V1)
├── Skills             → 11 capacidades com contrato
│     ↓ delegam em
├── Tools/Services     → handlers do worker + serviços (zero duplicação)
├── Sources            → discovery (rss, YouTube, crossref, arquivo…)
└── Human Gate         → aprovação/confirm humano (intransponível)
```

## Skills (AMENDMENT-2026-10-01-012)

| Skill | Status | Delega para | Payload obrigatório |
|---|---|---|---|
| `research` (Research Reach) | ✅ | `DISCOVERY_SCAN` (incl. YouTube) | workspace_id, profile_id |
| `factuality` (Evidence Analyzer) | ✅ | `CLAIM_VERIFICATION` | workspace_id, profile_id |
| `scripting` (Editorial Scripting) | ✅ | `CONTENT_GENERATION` (LLM) | package_id |
| `image_inspection` | ✅ | `IMAGE_ANALYSIS` | asset_ids |
| `platform_policy` | ✅ | `publisher_gate` (check-only) | package_id |
| `publication` | ✅ | `EXPORT` → PENDING | package_id, platform |
| `analytics` | ✅ | `ANALYTICS_SYNC` | publication_id, metrics |
| `factuality_challenge` | ✅ | `SocialIntelligenceService.research_challenge` (§11) | challenge_id |
| `visual_direction` | 📋 DECLARED | render roda no export (Doc 13) | — |
| `seo` | 📋 DECLARED | CopywriterSEO no draft | — |
| `music` | 📋 DECLARED | V2 (Doc 13) | — |

Cada skill valida o payload antes de invocar (`required_payload_keys`) e
roda com o ExecutionContext do chamador (isolamento workspace/profile).

## Recipes V1

| Recipe | Fluxo | Human Gate |
|---|---|---|
| `prepare_publication` | scripting (opcional) → platform_policy → publication | `POST /api/v1/publications/{id}/confirm` |
| `factuality_audit` | factuality | nenhum (recálculo auditado) |
| `research_sweep` | research | nenhum (coleta não publica) |
| `factuality_challenge` | research → factuality_challenge | `POST /api/v1/social/challenges/{id}/review` |

O step `scripting` é **opcional**: sem `GOOGLE_AI_API_KEY` a recipe segue
sem proposta de LLM (o rascunho pode ser escrito à mão na UI).

## Garantias permanentes

1. **Human Gate intransponível** — nenhuma recipe publica: publication
   termina em PENDING; confirm é humano (Emenda 007).
2. **Prompt não é governança** — a saída do LLM passa por schema + gate
   semântico + QC (Doc 17 §10).
3. **Skills delegam, nunca duplicam** — a lógica única vive nos handlers/
   serviços já auditados.
4. **Seleção de skills por LLM só com benchmark + approval** (Doc 17 §9/§15).
5. Nova recipe = novo código revisado (PR), não comportamento autônomo.
