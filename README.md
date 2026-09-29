# URDIA — History Intelligence Layer (HIL)

Motor de **Inteligência Editorial Histórica**. Produto inicial: **Antigo Mundo Novo**.

> **DESCUBRA MUITO. AFIRME POUCO. PROVE O QUE AFIRMAR. MOSTRE O QUE NÃO SABE. CONTE SOMENTE O QUE MERECE SER CONTADO. APRENDA COM O RESULTADO.**

---

## O que é

O HIL não é um gerador simples de posts. É um pipeline editorial completo:

```text
DESCOBRIR → PESQUISAR → ORGANIZAR → CONFRONTAR → VERIFICAR → ENTENDER → DECIDIR → CRIAR → ADAPTAR → PUBLICAR → MEDIR → APRENDER
```

Nunca considerar LLM output como fato por si só. O sistema tem capacidade explícita de `NÃO PUBLICAR`.

## Fonte de verdade

A **Constituição** (`docs/constitution/00_HIL_MASTER_CONSTITUTION_V1.0.md`) é a fonte de verdade do produto e da arquitetura. Os Documentos 01–16 transformam essa constituição em implementação.

Leia na ordem definida em [`docs/constitution/README_START_HERE.md`](docs/constitution/README_START_HERE.md).

### Regra de autoridade

Quando houver contradição:

```text
NÃO INVENTAR
↓
IDENTIFICAR A CONTRADIÇÃO
↓
REGISTRAR AMENDMENT REQUIRED
↓
NÃO ALTERAR A CONSTITUIÇÃO SILENCIOSAMENTE
```

Mudanças seguem o template em `docs/constitution/AMENDMENT_TEMPLATE.md` e são registradas em `docs/amendments/AMENDMENT-YYYY-MM-DD-NNN.md`.

## Stack

```text
Python / FastAPI / Uvicorn / Pydantic / SQLAlchemy / Alembic
PostgreSQL / pgvector
React / TypeScript / Vite / Tailwind
HTTPX / Trafilatura / Scrapy / Playwright
Pillow / SVG / FFmpeg
DuckDB
```

Provider-agnostic. Desktop-first / Windows / Local-first.

## Estrutura do monorepo

```text
urdia-hil/
├── apps/
│   ├── api/        # HTTP, auth foundation, scope resolution, commands/queries
│   ├── worker/     # jobs, checkpoints, retries, orchestration
│   └── web/        # UI; nunca acessa DB/provider diretamente
├── packages/
│   ├── contracts/  # schemas
│   ├── domain/     # regras e entidades
│   ├── providers/  # adapters substituíveis
│   ├── research/   # discovery/research/extraction
│   ├── rendering/  # image/carousel/microloop
│   ├── governance/ # policy/capabilities/permissions/gates/audit
│   └── shared/
├── agents/
├── config/
├── templates/
├── assets/         # originals / derived / cache / exports / temp
├── scripts/
├── tests/
├── docs/           # constitution + amendments
├── migrations/
├── docker/
└── .github/workflows/
```

## Instalação e execução

Pré-requisitos: Git, Docker Desktop, Python, Node.js, FFmpeg.

```bash
cp .env.example .env        # definir POSTGRES_PASSWORD e demais variáveis
docker compose up -d postgres
alembic upgrade head
python -m scripts.seed
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
python -m apps.worker
cd apps/web && npm install && npm run dev
```

Health check: `GET /api/v1/health`

## Segurança obrigatória

Aplicar desde a primeira linha: menor privilégio; isolamento por workspace/profile; fail-closed para autorização, rights e publicação; secrets fora do código, prompts, logs e frontend; validação de schema + semântica + policy; proteção contra prompt injection, SSRF, path traversal, command injection e SQL injection; audit trail append-only; checkpoints/recovery de jobs; fallback sem perda de evidência.

Regra absoluta de direitos: **`UNKNOWN = NÃO PUBLICAR`**.

## Regras inegociáveis

Não inventar; não mascarar incerteza; não publicar sem rights identificado; não tratar cópia como independência; não copiar concorrentes; não publicar só porque está viral; não preencher calendário por volume; não deixar plataforma/provider/agente controlarem tudo; não contaminar profiles; não transformar resultado isolado em regra; não esconder erro; não confundir hipótese com fato.
