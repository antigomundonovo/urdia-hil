# RUNBOOK — Operação do URDIA HIL (Documento 07)

## Subir o ambiente (dia a dia)

```bash
# 1. Docker Desktop aberto (banco de dados)
docker compose up -d postgres

# 2. Migrações + seed (só quando houver mudança ou primeira vez)
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m scripts.seed

# 3. API (terminal 1)
.venv/Scripts/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

# 4. Interface (terminal 2)
cd apps/web && npm run dev   # → http://localhost:5173

# 5. Worker residente (terminal 3, opcional — processa jobs do radar)
.venv/Scripts/python -m apps.worker
```

## Health check

`GET http://127.0.0.1:8000/api/v1/health` → HEALTHY / DEGRADED (sem banco).

## Rotinas agendáveis (Doc 07 — Windows Task Scheduler)

- `python -m apps.worker --once` — varre(fontes)/processa jobs pontuais
- `python -m scripts.backup database` — backup do banco (recomendado: diário)
- `python -m scripts.backup assets` — backup de imagens originais/derivadas
- `python -m scripts.benchmark` — suite de benchmarks (Doc 16)

## Fila de jobs (urdia-enqueue)

Jobs são criados por rotinas internas e pela ferramenta de operação — a
constituição não expõe endpoint público de criação (Doc 02: só GET/retry/cancel).

```bash
# enfileirar um job (payload ganha eco de workspace/profile automaticamente)
urdia-enqueue --type DISCOVERY_SCAN --workspace <uuid> --profile <uuid> \
              --payload '{"source_id": "..."}' --priority 5

# tipos aceitos = enum JobType (Doc 03); ver apps/worker/__main__.py
urdia-enqueue --list            # 20 jobs mais recentes
python -m apps.worker --once    # processa um ciclo
```

Fail-closed: payload sem os ids obrigatórios falha o job sem retry (Doc 03);
provider indisponível/rate-limit reenfileira com checkpoint. Registro completo
de handlers reais vs stubs: `apps/worker/handlers_new.py` (docstring) e

## Backups (Doc 07)

```bash
python -m scripts.backup database           # → backups/db-YYYYMMDD-HHMMSS.sql
python -m scripts.backup assets             # → backups/assets-YYYYMMDD-HHMMSS.zip
python -m scripts.backup verify backups/db-XXXX.sql
python -m scripts.backup restore backups/db-XXXX.sql
```

## Recuperação (Doc 07 recovery order)

```text
parar workers → backup do estado atual → restaurar DB → restaurar assets
essenciais → alembic upgrade head → subir → health check
```

Jobs `RUNNING` órfãos são reenfileirados com checkpoint no próximo start do
worker (nunca apagados).

## Atualizações (Doc 07)

`backup → testes (pytest) → migration (alembic upgrade head) → health check`

## Segredos

Nunca em Git, logs, prompts, frontend, auditoria ou backups. `.env` é
local e gitignored.
