# URDIA HIL — checkpoint geral para continuidade

> ⚠️ **SUPERADO (2026-10-01):** este handoff descreve o estado de 2026-09-30
> (commit `4170b2e`), inclusive o caminho local antigo
> (`copilot-worktrees/...`, hoje `C:\urdia-hil`). A referência atual de
> continuidade é **[`docs/CHECKPOINT_2026-10-01.md`](CHECKPOINT_2026-10-01.md)**.
> Mantido como histórico.

**Atualizado em:** 2026-09-30  
**Branch de trabalho:** `antigomundonovo-continuar-projeto`  
**Commit no momento deste checkpoint:** `4170b2e2bb3f385344a48978f4ff92660d88f039`  
**Repositório:** `antigomundonovo/urdia-hil`  
**Estado verificado:** `HEAD` local e remoto iguais; worktree limpa.

Este documento é um handoff portátil para outra conversa, agente ou IA. Leia-o
junto com `docs/constitution/00_HIL_MASTER_CONSTITUTION_V1.0.md` e os
documentos 01–17, que continuam sendo a especificação autoritativa do produto.
Este handoff resume o estado conhecido; não substitui a constituição.

## Instrução inicial para a próxima IA

Continue o URDIA no branch existente `antigomundonovo-continuar-projeto`.
Primeiro confira `git status`, `git log` e este handoff; preserve alterações
preexistentes e nunca use a cópia principal como checkout de trabalho. Siga
`docs/constitution/17_CODE_AGENT_MASTER_EXECUTION.md` e a ordem de prioridade
nele definida. Implemente marcos pequenos e coerentes, sem criar regras,
estados, providers, endpoints ou formatos sem especificação ou amendment.
Rode testes adequados, registre limitações reais e, após cada marco grande,
faça commit no branch atual, push para `origin` e confirme que os SHAs local e
remoto coincidem. Não peça decisões rotineiras ao usuário; preserve autoridade
editorial humana, segurança, isolamento, direitos e comportamento fail-closed.

## Branch, checkout e banco

- Worktree desta sessão:
  `C:\Users\LucasSilvaRelieve\copilot-worktrees\urdia-hil\antigomundonovo-fuzzy-fiesta`
- Outra cópia do usuário:
  `C:\Users\LucasSilvaRelieve\urdia-hil`
- A outra cópia contém `.env` e o banco de desenvolvimento, mas historicamente
  não continha todos os scripts atuais. Não confundir imports nem executar
  comandos de código a partir dela sem apontar explicitamente para a worktree.
- O banco PostgreSQL de desenvolvimento já conectou com sucesso; Alembic chegou
  à revisão `0009`. Não apagar o volume Docker nem executar limpeza destrutiva.
- Para validar sem alterar dados do usuário, foi possível subir um PostgreSQL
  descartável Docker em porta local alternativa, migrá-lo até `head`, rodar
  testes e removê-lo. Não guardar senhas em código, logs, argumentos persistentes
  ou checkpoints.
- A entrega de email foi diagnosticada anteriormente como não configurada
  (`EMAIL_DELIVERY=NOT_CONFIGURED`); validar o ambiente antes de depender dela.

## O que o projeto já contém

O URDIA HIL é uma infraestrutura editorial histórica com foco em proveniência,
isolamento por workspace/perfil, direitos, gates determinísticos e aprovação
humana. O repositório tem uma aplicação Python/FastAPI, domínio/serviços,
worker, PostgreSQL/pgvector e uma UI React/TypeScript. A base inclui:

- autenticação por email/senha, sessões opacas em cookie HttpOnly, verificação
  de email e reset de senha (migrations conhecidas até `0009`);
- APIs e serviços para fontes, descoberta, claims/evidências, oportunidades,
  conteúdo editorial, QC, aprovação, exportação, analytics, aprendizado e jobs,
  com diferentes níveis de completude;
- adaptadores para algumas fontes e políticas de escopo por workspace/perfil;
- exportação manual em ZIP com validação de direitos/proveniência;
- Laya como capability opcional de classificação consultiva e ferramenta shadow
  de avaliação; não é autoridade editorial nem é ativada automaticamente.

O estado não equivale a produto completo: renderização de formatos, vários
handlers/jobs, agentes e orquestração, integrações OAuth/plataformas,
sincronização de analytics e várias superfícies editoriais ainda precisam ser
conferidas contra suas especificações.

## Marcos recentes e commits confirmados

- `395e88f245941185b971bf2570c6c5efee078606` — adapter Laya opcional, consultivo,
  com atribuição/licença e sem copiar código ou pesos do projeto upstream.
- `d622493f8ca266f50f4579c577fc6d9569c020e2` — avaliador shadow local sobre
  JSONL com rótulos revisados; métricas e hash de dataset, sem promover gates.
- `4170b2e2bb3f385344a48978f4ff92660d88f039` — recuperação de pacote editorial
  após refresh, restauração do rascunho/QC e isolamento de workspace.

O branch tem ainda um histórico maior de trabalho anterior: operação e
diagnóstico, jobs, auth, política de integração externa no logout, adapters de
fontes, segurança da exportação, UI de oportunidades, claims e verificação de
QC. Veja `git log --oneline` para a história completa em vez de inferir o estado
por uma lista parcial de SHAs.

## Último marco implementado

O commit `4170b2e`:

- adiciona `GET /api/v1/content/{package_id}` com o pacote canônico, drafts,
  variantes e último QC;
- identifica se o QC ainda é atual comparando o fingerprint com os dados
  presentes;
- expõe o ID do pacote mais recente no detalhe da oportunidade, para a UI
  encontrá-lo novamente após refresh;
- reidrata o último rascunho e claims selecionadas no editor;
- evita QC/aprovação na UI quando o pacote ainda carrega ou o rascunho foi
  alterado localmente sem ser salvo; aprovação e exportação continuam
  revalidando condições no servidor;
- retorna 404 quando o pacote solicitado pertence a outro workspace;
- documenta o contrato e estende o teste do fluxo completo.

Arquivos deste marco: `apps/api/content_routes.py`,
`apps/api/opportunities_routes.py`, `apps/web/src/api.ts`,
`apps/web/src/pages/OpportunityDetail.tsx`,
`docs/constitution/02_DATABASE_CONTRACTS_APIS.md` e
`tests/test_content_api.py`.

## Verificações e limitações conhecidas

Para o último marco, verificações executadas:

- `tests/test_content_api.py`: **5 passed** em banco PostgreSQL descartável com
  migrations até `0009`;
- `npm run typecheck`: passou;
- `npm run build`: passou;
- Ruff, `compileall` e `git diff --check`: passaram;
- o container descartável foi removido; o banco de desenvolvimento não foi
  alterado.

Em um marco Laya anterior, 12 testes específicos passaram e Ruff passou. A suíte
Python completa daquele marco demorou sem avançar em testes de jobs/DB e foi
interrompida; portanto não declarar que a suíte completa mais recente passou.
Há validações históricas anteriores de suite/benchmark, mas devem ser
reexecutadas antes de uma alegação atual de saúde global.

O handoff que motivou esta continuação registrou uma estimativa aproximada de
**55% feito / 45% faltante**, baseada numa auditoria anterior ao trabalho Laya
e à recuperação de pacotes. Não é uma medição atual nem deve ser repetida como
precisa sem reavaliar o roadmap 17 e o código/testes.

## Gaps a reavaliar e priorizar

Use como mapa inicial, não como auditoria atualizada:

1. Comparar os contratos dos documentos 00–17 com rotas, serviços, UI e testes;
   separar funcionalidade intencionalmente manual de lacuna real.
2. Cobrir os tipos de jobs e recuperação/restart definidos no Documento 03;
   handlers ainda parecem incompletos em relação ao workflow inteiro.
3. Confrontar os agentes, prompts versionados e orquestração do Documento 05
   com o estado de `agents/`, `config/` e `templates/`.
4. Renderer de imagem/carrossel/Microloop: `packages/rendering` foi identificado
   anteriormente como essencialmente vazio; verificar se houve mudança.
5. Cobertura de UI/API para gestão de assets, investigação, claims/evidências e
   Story Graph.
6. OAuth e integrações concretas de plataformas, publicação e confirmação
   manual; não escolher providers sem decisão/spec. Publicação deve permanecer
   manual e com gates humanos enquanto integração segura não existir.
7. Sincronização de métricas/comentários; analytics manual não equivale a
   integrações completas.
8. Rever amendments 001–010 e a constituição: 002–007 foram reportados como
   propostas aguardando decisão; 001 pode estar superado pela auth posterior.
   Não marcar decisões como aprovadas em nome do usuário.
9. Revalidar autenticação, CSRF, reset/verificação, backups/restore, upload,
   SSRF, path traversal, isolamento por workspace/perfil e os testes
   non-negotiable listados no Documento 17.
10. Avaliação real Laya permanece pendente até existir dataset de rótulos
    revisados/aprovados; não inventar rótulos nem baixar checkpoints sem
    necessidade explícita. Laya permanece opcional e consultivo.

## Arquivos de referência prioritários

- `docs/constitution/00_HIL_MASTER_CONSTITUTION_V1.0.md` — fonte de verdade.
- `docs/constitution/02_DATABASE_CONTRACTS_APIS.md` — contratos da API.
- `docs/constitution/03_WORKFLOWS_JOBS_STATES_ACCEPTANCE.md` — jobs e estados.
- `docs/constitution/05_AGENTS_PROMPTS_ORCHESTRATION.md` — agentes e prompts.
- `docs/constitution/08_SECURITY_INTEGRATION_BOUNDARIES.md` — limites de
  segurança e integrações.
- `docs/constitution/09_RESEARCH_DISCOVERY.md` — pesquisa e descoberta.
- `docs/constitution/13_CONTENT_RENDERING.md` — formatos/renderização.
- `docs/constitution/14_PLATFORM_ADAPTERS.md` — providers/plataformas.
- `docs/constitution/17_CODE_AGENT_MASTER_EXECUTION.md` — ordem de execução e
  definição de pronto.
- `docs/LAYA_INTEGRATION.md` e
  `docs/amendments/AMENDMENT-2026-09-30-010.md` — limites/licença Laya.
- `apps/api/content_routes.py`, `apps/api/opportunities_routes.py`,
  `packages/research/content.py`,
  `apps/web/src/pages/OpportunityDetail.tsx`,
  `tests/test_content_api.py` — fluxo de conteúdo corrente.

## Regra de conclusão dos próximos marcos

Antes de alterar, verifique branch e worktree. Leia especificação e prior art.
Faça a menor mudança coerente que complete um fluxo, atualize documentação
diretamente relacionada e teste o requisito exato. Não enfraqueça isolamento,
direitos, proveniência, confirmação humana nem comportamento fail-closed. Para
cada marco grande, rode validações pertinentes, examine o diff, faça commit
com o trailer de coautoria configurado no repositório/sessão, envie ao remoto e
confirme igualdade dos SHAs. Registre no próximo handoff a mudança, os testes e
as limitações sem alegar sucesso não verificado.
