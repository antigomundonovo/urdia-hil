# URDIA-HIL — Social & Audience Intelligence

Camada de **Inteligência Social e de Audiência** do ecossistema URDIA. O HIL trata comentários, Social Inbox, triagem, demanda, feedback, oportunidades, Audience Pulse, Response Debt e factuality challenges, mantendo uma fronteira explícita com o URDIA Studio, que é responsável pelo pipeline de vídeo.

> **DESCUBRA MUITO. AFIRME POUCO. PROVE O QUE AFIRMAR. MOSTRE O QUE NÃO SABE. CONTE SOMENTE O QUE MERECE SER CONTADO. APRENDA COM O RESULTADO.**

---

## O que é

O HIL não é um gerador de vídeo nem uma cópia do Studio. Ele é a camada social/audience que transforma sinais da audiência em informação estruturada e auditável:

```text
AUDIÊNCIA → COMENTÁRIOS → TRIAGEM → DEMANDA → FEEDBACK → INTELIGÊNCIA → DECISÃO HUMANA → STUDIO/HIL
```

Nunca considerar comentário ou saída de LLM como evidência por si só. O sistema preserva a capacidade explícita de `NÃO PUBLICAR` e exige revisão humana para decisões externas.

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

Provider-agnostic. **Web-first** (browser: FastAPI + React/Vite) / Windows dev / Local-first — os dados e segredos permanecem na máquina do operador.

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

O autorregistro (`POST /api/v1/auth/register`) só funciona com
`APP_ENV=development` ou `test`; nos demais ambientes retorna **503**, com ou
sem SMTP. Mantenha a aplicação local em `127.0.0.1`: esse controle depende de
configuração de ambiente, não de uma verificação de que o cliente é local.
Não use `development` para contornar o bloqueio em produção.

Na interface, informe e-mail, senha de pelo menos 12 caracteres e aceite os
Termos de Uso e a Política de Privacidade (`accepted_terms=true`). A aceitação
registra data e versão. Cada novo cadastro cria workspace privado e perfil.

| Configuração local | Resultado do cadastro | Como acessar |
|---|---|---|
| Sem SMTP (deixe `SMTP_HOST` e `SMTP_FROM_EMAIL` vazios) | Conta marcada como verificada; HTTP 200, cookie e contexto de sessão | Acesso imediato; em acessos posteriores, entrar com e-mail e senha |
| Com `SMTP_HOST` **e** `SMTP_FROM_EMAIL` preenchidos | Conta não verificada; HTTP 202, sem sessão; envio em segundo plano | Abrir o link recebido, confirmar e então entrar com e-mail e senha |

A seleção do fluxo verifica apenas a presença dessas duas variáveis, não a
entrega de mensagens. SMTP parcial é configuração inválida para operação:
preencha ambos para testar e-mail. Falha de entrega não libera acesso imediato;
verifique o serviço e solicite novo link em `/api/v1/auth/verification/request`.
A resposta 202 é genérica e não comprova envio nem criação de conta (inclusive
para endereço já cadastrado). O link de confirmação vale 24 horas, é de uso
único e não cria sessão; `/api/v1/auth/verification/confirm` confirma o token.

Configure também `FRONTEND_BASE_URL` e as origens permitidas em `CORS_ORIGINS`.
Se exigidos pelo servidor, defina `SMTP_USERNAME`/`SMTP_PASSWORD`. Mensagens usam
STARTTLS por padrão; para TLS implícito, use `SMTP_USE_SSL=true` e a porta
correspondente (normalmente 465). Recuperação de senha por link de uso único
requer SMTP funcional, inclusive para contas locais criadas sem SMTP.

A sessão usa cookie HttpOnly com expiração de 12 horas; **Sair** a revoga.
Endpoints de dados exigem sessão válida e membership no workspace.
As credenciais sociais são separadas da conta URDIA: o Instagram usa token
configurado no backend; isso não equivale a um fluxo OAuth de Instagram na UI.
O TikTok possui rotas OAuth próprias, sujeitas às condições da
[matriz de capacidades](docs/PLATFORM_CAPABILITIES.md).

Em produção, mantenha o autorregistro desabilitado, use
`FRONTEND_BASE_URL` com HTTPS e SMTP criptografado. Cadastro público continua
condicionado a trabalho adicional de segurança, incluindo rate limiting
compartilhado entre processos e MFA; configurar SMTP não remove esse bloqueio.

### Primeira publicação no Instagram

1. Prepare o conteúdo, identifique os direitos, conclua QC e aprovação humana
   e exporte o pacote pelo fluxo normal. Use a publicação `PENDING` criada
   nesse fluxo, no workspace/perfil da sessão; não crie registros manualmente.
2. Configure `META_INSTAGRAM_TOKEN` no `.env` do backend com token válido e
   permissões oficiais de publicação para a conta desejada. Registre a
   expiração em `META_INSTAGRAM_TOKEN_EXPIRES_AT` e renove antes de vencer.
   `META_APP_ID`/`META_APP_SECRET` pertencem à configuração do app; não substituem
   o token. Reinicie os processos após alterar o ambiente.
3. Hospede as imagens em URLs acessíveis pela Meta. Envie `public_image_urls`
   na ordem desejada; se omitidas, a rota tenta hospedar as imagens exportadas
   usando o asset host configurado. Caminhos locais não funcionam.
4. Após revisar conta, legenda e mídias, a ação humana de publicação chama
   `POST /api/v1/publications/{id}/publish?workspace_id=<uuid>` com sessão
   autenticada e corpo `{"profile_id":"<uuid>","public_image_urls":["https://host/imagem.jpg"]}`.
   Foto usa uma imagem; carrossel usa 2–10. A legenda vem do último rascunho
   (título + legenda); `caption_override`, se usado, também exige revisão.
5. Confira `status=PUBLISHED`, `remote_id` e o post na conta correta; o permalink
   pode estar ausente mesmo após sucesso. A API aguarda o container ficar
   pronto antes de publicar. Em falha, confira o estado local e a conta remota
   antes de tentar novamente, pois a chave local não garante deduplicação na Meta.

Sem credenciais ou hospedagem pública, utilize o kit manual do export e,
somente depois de postar, registre a confirmação em
`POST /api/v1/publications/{id}/confirm`. Essa confirmação registra uma postagem
manual; não é a chamada que envia conteúdo à API do Instagram.
A validação real de 04/10/2026 registrada na matriz é histórica; não comprova
que o token atual esteja válido nem que outro ambiente esteja habilitado.

## Segurança obrigatória

Aplicar desde a primeira linha: menor privilégio; isolamento por workspace/profile; fail-closed para autorização, rights e publicação; secrets fora do código, prompts, logs e frontend; validação de schema + semântica + policy; proteção contra prompt injection, SSRF, path traversal, command injection e SQL injection; audit trail append-only; checkpoints/recovery de jobs; fallback sem perda de evidência.

Regra absoluta de direitos: **`UNKNOWN = NÃO PUBLICAR`**.

## Regras inegociáveis

Não inventar; não mascarar incerteza; não publicar sem rights identificado; não tratar cópia como independência; não copiar concorrentes; não publicar só porque está viral; não preencher calendário por volume; não deixar plataforma/provider/agente controlarem tudo; não contaminar profiles; não transformar resultado isolado em regra; não esconder erro; não confundir hipótese com fato.
