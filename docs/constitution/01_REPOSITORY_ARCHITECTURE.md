# DOCUMENTO 01 — REPOSITORY + SERVICE ARCHITECTURE

## Stack
```text
Python / FastAPI / Uvicorn / Pydantic / SQLAlchemy / Alembic
PostgreSQL / pgvector
React / TypeScript / Vite / Tailwind
HTTPX / Trafilatura / Scrapy / Playwright
Pillow / SVG / FFmpeg
```

## Monorepo
```text
urdia-hil/
├── apps/
│   ├── api/
│   ├── worker/
│   └── web/
├── packages/
│   ├── contracts/
│   ├── domain/
│   ├── providers/
│   ├── research/
│   ├── rendering/
│   ├── governance/
│   └── shared/
├── agents/
├── config/
├── templates/
├── assets/
├── scripts/
├── tests/
├── docs/
├── migrations/
├── docker/
└── .github/workflows/
```

## Responsabilidades
- `apps/api`: HTTP, auth foundation, scope resolution, commands/queries.
- `apps/worker`: jobs, checkpoints, retries, orchestration.
- `apps/web`: UI; nunca acessa DB/provider diretamente.
- `packages/domain`: regras e entidades.
- `packages/contracts`: schemas.
- `packages/providers`: adapters substituíveis.
- `packages/research`: discovery/research/extraction.
- `packages/rendering`: image/carousel/microloop.
- `packages/governance`: policy/capabilities/permissions/gates/audit.

## Dependency Rules
Permitido:
```text
API → Domain → Governance/Providers
Worker → Domain/Agents/Providers
Agent → Contracts + approved capabilities
Web → API
```
Proibido:
```text
Web → DB
Web → LLM
OpenClaw → DB
Hermes → DB
Agent → raw credentials
Publisher → non-READY
```

## Execution Context
```python
ExecutionContext(
  workspace_id,
  profile_id,
  actor_id,
  job_id,
  capability,
  correlation_id,
)
```

## Profile Configuration
Nunca hardcode ANM em regras de domínio. Use `profile_id` + configuração do profile.

## Security
- least privilege;
- zero trust entre componentes;
- server-side validation;
- profile isolation;
- secret redaction;
- fail closed;
- audit;
- resource limits;
- dependency/license review.

## Definition of Done
API, web, DB, migrations, profile, registries, jobs, audit e primeiro vertical slice funcionais.
