# URDIA — HISTORY INTELLIGENCE LAYER
## PRODUCT + ARCHITECTURE + EDITORIAL CONSTITUTION

**Versão:** 1.0  
**Status:** BASELINE CONGELADA  
**Produto inicial:** Antigo Mundo Novo  
**Controladora:** URDIA  
**Ambiente:** Desktop-first / Windows / Local-first

---

# 1. FUNDAÇÃO

O HIL não é um gerador simples de posts. É um **Motor de Inteligência Editorial Histórica**.

Pipeline:
```text
DESCOBRIR
↓
PESQUISAR
↓
ORGANIZAR
↓
CONFRONTAR
↓
VERIFICAR
↓
ENTENDER
↓
DECIDIR
↓
CRIAR
↓
ADAPTAR
↓
PUBLICAR
↓
MEDIR
↓
APRENDER
```

Nunca considerar LLM output como fato por si só.

# 2. NORTH STAR

> “Qual história merece ocupar um espaço no feed do Antigo Mundo Novo?”

Não otimizar somente viralização. O sistema precisa ter capacidade explícita de `NÃO PUBLICAR`.

# 3. PROFILE INICIAL — ANTIGO MUNDO NOVO

Tema: História, curiosidades, memória, cultura histórica e descobertas relacionadas ao passado e ao patrimônio humano.

Configuração:
```yaml
language: pt-BR
audience: Brasil
brazil_weight: 0.65
world_weight: 0.35
historical_depth: 7
editorial_style: acessível + curioso + documental
image_first: true
real_historical_assets_first: true
ai_imagery: secondary
uncertainty: required
political_policy: neutral_evidence_based
human_approval_required: true
automation_level: 2
unknown_rights_block_publication: true
```

65/35 é prioridade de descoberta, não cota rígida de publicação.

# 4. ESCOPO

Pode abranger história do Brasil e do mundo, pessoas famosas e comuns, guerras, diplomacia, arqueologia, ciência, tecnologia, medicina histórica, arquitetura, cidades, objetos, documentos, fotografias, arte, literatura, música, costumes, alimentação, vestuário, indústria, transporte, patrimônio, mistérios documentados, história da ciência, história recente com valor documental e What If explicitamente identificado.

# 5. NÃO É

Não é inicialmente:
- editor de vídeo longo;
- gerador de Shorts narrados;
- voice-over engine;
- clipping system;
- crawler de toda a internet;
- copiador de concorrentes;
- máquina de publicação indiscriminada;
- previsão garantida de viralização.

Único vídeo nativo: **MICROLOOP**, composto por imagem + texto + movimento mínimo opcional + áudio opcional, em aproximadamente 5–12s.

# 6. MULTIPROFILE

```text
URDIA
├── User
├── Workspace
├── Profile
├── Channel Accounts
├── Editorial Policy
├── Knowledge Scope
├── Memory
├── Assets
└── Analytics
```

Regra:
> **Compartilhar capacidade não significa compartilhar contexto.**

Camadas:
- Common Knowledge;
- Shared Learning generalizado e aprovado;
- Private Profile Intelligence.

# 7. ISOLAMENTO

Toda operação relevante carrega `workspace_id`, `profile_id` e `scope` quando aplicável.

Profile B nunca pode enxergar dados privados de Profile A.

# 8. AGENTES

- OpenClaw = operador/orquestrador externo via API;
- Hermes = pesquisador/memória auxiliar, nunca fonte canônica;
- JEV = recomendação estruturada, nunca autoridade final;
- MiroFish = laboratório de simulação, não fonte factual.

Nenhum agente possui autoridade completa.

# 9. CAMADAS HIL

```text
Discovery
Source Intelligence
Historical Knowledge
Evidence / Provenance
Fact Check / Uncertainty
Editorial Intelligence
Format Intelligence
Platform Intelligence
Visual Intelligence
Rights
Production
QC
Human Review
Publishing
Analytics
Learning
Governance
Operations
```

# 10. OPPORTUNITY / STORY / CONTENT PACKAGE

A unidade central é `Opportunity`. Ela relaciona stories, entities, claims, sources, evidence, assets, rights, riscos, formatos, plataformas, drafts, publications e decisões.

`Story` representa a história potencialmente contada.

`Content Package` é a manifestação editorial de uma story.

# 11. CANONICAL CONTENT

Todos os formatos partem de:
```text
factual core
claims
source references
editorial angle
key message
visual assets
CTA policy
SEO entities
```

Depois:
```text
Canonical Content → Platform Adapter → Platform Variant
```

# 12. EVIDENCE

Modelo:
```text
CLAIM
↓
EVIDENCE
↓
SOURCE
↓
PROVENANCE
```

Estados de conhecimento:
```text
SABEMOS
ACREDITAMOS
INTERPRETAMOS
NÃO SABEMOS
```

Estados de incerteza:
```text
CONFIRMADO
PROVÁVEL
POSSÍVEL
CONTROVERSO
DESCONHECIDO
REFUTADO
```

Não encontrado ≠ não aconteceu.

# 13. CONFLITO E ADVERSARIAL RESEARCH

Se fontes divergem: separar claims, buscar fonte primária, avaliar independência, preservar versões e marcar incerteza.

Claims fortes devem ser atacados:
```text
primeiro / único / nunca / sempre / mais antigo / maior / origem / causou
```

# 14. PHOTO STORY

```text
IMAGE
↓ HASH / PERCEPTUAL HASH / EXIF / OCR / VISION / EMBEDDING
↓
VISUAL SEARCH / ARCHIVE SEARCH / SOURCE MATCHING
↓
HISTORICAL CONTEXT
↓
RIGHTS
↓
STORY
↓
OPPORTUNITY
```

Similaridade visual não prova identidade.

# 15. DIREITOS

Classes:
```text
PUBLIC_DOMAIN
CC0
CC_BY
CC_BY_SA
OTHER_FREE_LICENSE
PERMISSION_REQUIRED
UNKNOWN
PROHIBITED
```

Regra absoluta:
```text
UNKNOWN = NÃO PUBLICAR
```

# 16. VISUAL

Classificações:
```text
ORIGINAL_AS_RETRIEVED
CROPPED
RESTORED
UPSCALED
COLORIZED
RECONSTRUCTED
AI_GENERATED
ILLUSTRATION
UNKNOWN
```

Real histórico primeiro; AI é secundária.

# 17. EDITORIAL INTELLIGENCE

Avaliar dimensões como:
```text
editorial_fit
historical_value
audience_relevance
novelty
visual_potential
conversation_potential
source_availability
rights_availability
production_feasibility
timing
saturation
repetition
uncertainty
risk
```

Não reduzir a uma nota mágica.

# 18. FORMATOS

Prioridade:
- foto histórica comentada;
- carrossel narrativo;
- carrossel documental;
- fonte contra fonte;
- timeline;
- documento histórico;
- mapa;
- objeto;
- pessoa esquecida;
- lugar histórico;
- pergunta/enquete/quiz;
- What If;
- série;
- microloop;
- especial.

# 19. COMPETIDORES

Usar concorrentes para detectar assuntos, formatos, perguntas e gaps. Nunca como texto-base para cópia.

# 20. LEARNING

```text
DATA
↓
EXPERIENCE
↓
HYPOTHESIS
↓
EXPERIMENT
↓
RESULT
↓
RULE CANDIDATE
↓
HUMAN REVIEW
↓
RULE
```

# 21. QUALITY GATES

Antes de READY:
```text
RELEVANCE
EVIDENCE
FACTUALITY
UNCERTAINTY
RIGHTS
ORIGINALITY
VISUAL
SEO
PLATFORM
ANTI-SLOP
HUMAN_REVIEW
```

# 22. PUBLICATION

V1 exige aprovação humana.

Publisher só recebe conteúdo que esteja:
```text
READY
+
APPROVED
+
RIGHTS_VERIFIED
+
PLATFORM_ALLOWED
```

# 23. INFRAESTRUTURA

Base:
```text
Python
FastAPI
React
TypeScript
Vite
PostgreSQL
pgvector
DuckDB
HTTPX
Trafilatura
Scrapy
Playwright
Pillow
SVG
FFmpeg
```

Provider-agnostic.

# 24. GOVERNANCE

Capability Registry e Provider Registry controlam provider, capability, version, schema, quota, cost, privacy, license, health, fallback e allowed profiles.

# 25. STORAGE / BACKUP

```text
assets/originals
assets/derived
assets/cache
assets/exports
assets/temp
```

Backups devem incluir database e assets essenciais, nunca secrets.

# 26. ESTADOS

```text
DISCOVERED → NORMALIZED → CLUSTERED → CANDIDATE → RESEARCHING → EVIDENCE_COLLECTED → FACT_CHECK → UNCERTAINTY_REVIEW → OPPORTUNITY_SCORED → FORMAT_SELECTED → PLATFORM_SELECTED → DRAFTING → VISUAL_PRODUCTION → RIGHTS_CHECK → SEO_CHECK → QUALITY_CONTROL → HUMAN_REVIEW → READY → SCHEDULED → PUBLISHED → ANALYZING → LEARNING
```

Auxiliares:
```text
QUARANTINED
BLOCKED
NEEDS_RESEARCH
RIGHTS_BLOCKED
FACT_CHECK_FAILED
DUPLICATE
REJECTED
CANCELLED
```

# 27. PRIMEIRO VERTICAL SLICE

```text
FOTO HISTÓRICA
↓ ORIGEM
↓ DIREITOS
↓ CLAIMS
↓ EVIDENCE
↓ STORY
↓ OPPORTUNITY
↓ FORMAT
↓ POST/CAROUSEL/MICROLOOP
↓ QC
↓ HUMAN REVIEW
↓ EXPORT
```

# 28. PRINCÍPIOS INEGOCIÁVEIS

Não inventar; não mascarar incerteza; não publicar sem rights identificado; não tratar cópia como independência; não copiar concorrentes; não publicar só porque está viral; não preencher calendário por volume; não deixar plataforma/provider/agente controlarem tudo; não contaminar profiles; não transformar resultado isolado em regra; não esconder erro; não confundir hipótese com fato.

# 29. FRASE-CONTRATO

> **DESCUBRA MUITO. AFIRME POUCO. PROVE O QUE AFIRMAR. MOSTRE O QUE NÃO SABE. CONTE SOMENTE O QUE MERECE SER CONTADO. APRENDA COM O RESULTADO.**

# 30. AMENDMENT

Toda mudança deve registrar versão, data, motivo, impacto e decisão. Nunca alterar silenciosamente.
