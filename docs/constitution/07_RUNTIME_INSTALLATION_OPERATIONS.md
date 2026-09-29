# DOCUMENTO 07 — RUNTIME + INSTALLATION + OPERATIONS

## Environment
```text
Windows
Desktop-first
Local-first
```

## Prerequisites
```text
Git
Docker Desktop
Python
Node.js
FFmpeg
```

## Environment files
```text
.env
.env.example
```

Nunca versionar `.env`.

## Example variables
```env
APP_ENV=development
API_HOST=127.0.0.1
API_PORT=8000
WEB_PORT=5173
DATABASE_URL=postgresql+psycopg://urdia:${POSTGRES_PASSWORD}@localhost:5432/urdia
ASSET_ROOT=./assets
EXPORT_ROOT=./assets/exports
CACHE_ROOT=./assets/cache
TEMP_ROOT=./assets/temp
DEFAULT_PROFILE_KEY=antigo_mundo_novo
LOG_LEVEL=INFO
```

## Run
```text
docker compose up -d postgres
alembic upgrade head
python -m scripts.seed
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
python -m apps.worker
cd apps/web && npm install && npm run dev
```

## Health
```http
GET /api/v1/health
```

States:
`HEALTHY DEGRADED UNAVAILABLE QUOTA_LIMITED AUTH_ERROR POLICY_BLOCKED`.

## Storage
```text
assets/originals
assets/derived
assets/cache
assets/exports
assets/temp
```

## Backup
Provide scripts:
```text
backup_database
restore_database
backup_assets
verify_backup
```

## Recovery
```text
stop workers
→ backup current state
→ restore DB
→ restore essential assets
→ migrate/validate
→ start
→ health check
```

## Jobs
On restart, inspect `RUNNING` jobs, use checkpoint recovery and never silently delete job history.

## Crawler
Use timeout, size limits, redirect revalidation, cache, ETag, Last-Modified, rate limiting and robots handling. Never bypass CAPTCHA or auth controls.

## Windows Task Scheduler
Pode agendar discovery, analytics sync, backup, source revalidation e daily brief. Não exigir app aberto 24/7.

## Secrets
Never in Git, logs, prompts, frontend, audit or exports.

## Updates
```text
backup → test → migration → health
```

## Definition of Done
Install reproduzível + DB + API + worker + frontend + migrations + storage + providers + recovery + backup + restore + health + logs.
