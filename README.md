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

### Classificação auxiliar opcional

Laya pode ser habilitada como provider opcional de decisões tipadas, sempre
consultivas e sem autoridade sobre fatos, direitos, QC ou publicação. Instalação,
ativação explícita, limites e licença estão documentados em
[`docs/LAYA_INTEGRATION.md`](docs/LAYA_INTEGRATION.md); a instalação normal do
URDIA não instala essa dependência nem baixa modelos.

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
python -m scripts.doctor    # valida app env + conexão com o Postgres
# ou: urdia-doctor

docker compose up -d postgres
alembic upgrade head
python -m scripts.seed
# ou: urdia-seed

uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
python -m apps.worker
cd apps/web && npm install && npm run dev
```

Health check: `GET /api/v1/health`

Diagnóstico operacional: `python -m scripts.doctor` (ou `urdia-doctor`) imprime o ambiente e a URL do banco com senha mascarada para validar o bootstrap sem expor segredos em logs.

## Geração assistida (LLM opcional)

Configure `GOOGLE_AI_API_KEY` no `.env` (Google AI Studio) para habilitar a
geração assistida de rascunhos (agente Copywriter, Gemini) e a análise visual
de imagens. A saída do LLM é sempre uma **proposta**: passa por validação de
schema, gate semântico determinístico (só claims anexados e verificados), QC
e aprovação humana antes de qualquer publicação. Provider/modelo registrados
em [`docs/PROVIDERS.md`](docs/PROVIDERS.md); troca exige benchmark (Doc 17 §9/§15).

## Worker e fila de jobs

```bash
python -m apps.worker            # residente: processa a fila continuamente
python -m apps.worker --once     # processa um ciclo e sai (CI/testes)
urdia-enqueue --type DISCOVERY_SCAN --workspace <uuid> --profile <uuid>
urdia-enqueue --list             # 20 jobs mais recentes
```

Jobs são criados por rotinas internas e pela ferramenta de operação
`urdia-enqueue` (a constituição não expõe endpoint público de criação).
Cada job carrega checkpoint e retry classificado (Doc 03); jobs `RUNNING`
órfãos são reenfileirados no restart.

## Publicação (redes sociais)

Redes oficiais (AMENDMENT-011): **Instagram, Facebook, X (Twitter), YouTube,
TikTok, Threads, Kwai**. Política: rede com API oficial publica direto da
URDIA — **sempre após aprovação humana**; rede sem API (Kwai; posts de
comunidade do YouTube) recebe um **kit de postagem manual completo** no
export (`platform_variants/<rede>/MANUAL_POSTING.md`) e a publicação é
confirmada no sistema depois de feita. Matriz de capacidades e requisitos:
[`docs/PLATFORM_CAPABILITIES.md`](docs/PLATFORM_CAPABILITIES.md).

## Conta e sessão

Na interface, crie uma conta com e-mail e senha de pelo menos 12 caracteres.
Cada cadastro recebe um workspace privado e precisa confirmar o e-mail antes
de entrar. Configure `SMTP_HOST`, `SMTP_FROM_EMAIL` e, se exigido pelo servidor,
`SMTP_USERNAME`/`SMTP_PASSWORD` no `.env`; mensagens usam STARTTLS por padrão
(`SMTP_USE_SSL=true` habilita TLS implícito, normalmente na porta 465).
A sessão usa cookie HttpOnly com expiração de 12 horas; **Sair** a revoga.
Há fluxo de redefinição de senha por link de uso único. Endpoints de dados
exigem sessão válida e membership no workspace. Ainda não há conexão OAuth
com redes/plataformas; não exponha auto-cadastro publicamente até adicionar
rate limiting compartilhado entre processos e MFA. Em produção, use
`FRONTEND_BASE_URL` com HTTPS e configure o SMTP com STARTTLS ou TLS implícito
(`SMTP_USE_SSL=true`).

## Segurança obrigatória

Aplicar desde a primeira linha: menor privilégio; isolamento por workspace/profile; fail-closed para autorização, rights e publicação; secrets fora do código, prompts, logs e frontend; validação de schema + semântica + policy; proteção contra prompt injection, SSRF, path traversal, command injection e SQL injection; audit trail append-only; checkpoints/recovery de jobs; fallback sem perda de evidência.

Regra absoluta de direitos: **`UNKNOWN = NÃO PUBLICAR`**.

## Regras inegociáveis

Não inventar; não mascarar incerteza; não publicar sem rights identificado; não tratar cópia como independência; não copiar concorrentes; não publicar só porque está viral; não preencher calendário por volume; não deixar plataforma/provider/agente controlarem tudo; não contaminar profiles; não transformar resultado isolado em regra; não esconder erro; não confundir hipótese com fato.
