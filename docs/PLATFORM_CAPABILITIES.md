# Matriz de Capacidades de Plataformas (revisão de implementação: 2026-10-19)

> Complemento operacional do Doc 14 (lista oficial: AMENDMENT-2026-10-01-011).
> Política do dono: **rede com API oficial → publica direto da URDIA, sempre
> APÓS aprovação humana (confirm)**; rede sem API → o export gera um **kit de
> postagem manual completo** (texto, mídias, hashtags, passos) e a publicação
> é confirmada no sistema depois de feita à mão.
> Há adaptadores de publicação implementados para Instagram e TikTok. Isso
> não habilita automaticamente nenhuma conta/instalação. O catálogo declarativo
> e o registro genérico não representam o estado das rotas diretas de publicação.
> Ativação operacional exige credenciais oficiais, validação dos requisitos e
> teste de revogação (Doc 14). O E2E de Instagram de 04/10/2026 é um registro
> histórico; esta revisão não repetiu postagem real nem validou tokens atuais.

## Resumo

| Plataforma | Método-alvo | Capacidade declarada | Estado / condição operacional |
|---|---|---|---|
| Instagram | **API — E2E VALIDADO** ✅ 2026-10-04 | ✅ graph.instagram.com (photo/carousel) | adaptador implementado; E2E real registrado em 04/10; cada instalação exige token e imagens públicas |
| Facebook | **API** | ✅ Graph API (páginas) | sem adaptador de publicação conectado à rota atual; exige implementação e credenciais/permissões de página |
| X (Twitter) | **API** | ✅ API v2 (pay-per-use) | sem adaptador de publicação conectado à rota atual; exige implementação, conta dev e créditos |
| Threads | **API** | ✅ Threads API (2 passos) | sem adaptador de publicação conectado à rota atual; exige implementação e OAuth |
| TikTok | **API** | ✅ Content Posting API | adaptador e OAuth implementados; exige token, `video.publish`, privacidade permitida e auditoria para Direct Post público; sem E2E real comprovado nesta revisão |
| YouTube | **API** (vídeo) | ✅ Data API v3 `videos.insert` | sem adaptador de upload conectado à rota atual; exige implementação, projeto Google Cloud e OAuth |
| YouTube Community | **MANUAL** | ❌ sem API para posts de comunidade | — (kit manual no export) |
| Kwai | **MANUAL** | ❌ não existe API oficial de publicação (apenas Ads e leituras não-oficiais) | — (kit manual no export) |

Os limites, preços e requisitos externos abaixo são referências consultadas em
01/10/2026, não uma nova verificação da documentação das plataformas. Confira-os
no painel/documentação oficial antes da ativação; não são prova de suporte no código.

## Detalhes e limites por rede

### Instagram
- Fluxo: criar media container → `media_publish`. Carrossel conta como 1 post.
- Limite: 100 posts publicados via API por janela móvel de 24h.
- Backend implementado: `graph.instagram.com/v21.0`, `me/media` → polling de
  `status_code` até `FINISHED` → `me/media_publish`.
- Configure `META_INSTAGRAM_TOKEN` válido para a conta profissional e as permissões
  do fluxo Instagram utilizado. Não confundir este backend com integração via
  Facebook Login: a exigência de página vinculada depende do fluxo escolhido,
  não é checada pelo adaptador atual.
- Escopo implementado: `PHOTO_POST` (1 imagem) e `CAROUSEL` (2–10 imagens), legenda
  não vazia de até 2.200 caracteres. Reels/vídeo e coleta de analytics não estão
  implementados neste adaptador; o catálogo declarativo não comprova suporte.
- URLs HTTP(S) passam pela validação sintática, mas a acessibilidade pública real
  precisa ser conferida: a Meta baixa os arquivos; caminhos locais são rejeitados.

### Facebook
- Graph API publica em **páginas** (perfis pessoais não são suportados).
- Mesmo app Meta do Instagram (Login do Facebook).

### X (Twitter)
- 2026: sem tier gratuito/assinaturas para novos devs — **pay-per-use** por créditos.
- Custos: ~US$ 0,015 por tweet; ~US$ 0,20 quando contém link.

### Threads
- Fluxo: container → `threads_publish`.
- Limites: 500 caracteres por post; 250 posts/24h por perfil.

### TikTok
- Content Posting API: escopo `video.publish`.
- **Direct Post exige auditoria de app aprovada** — sem ela, o conteúdo vai como privado/apenas para si (inadequado para publicação final).

### YouTube
- Vídeo: OAuth 2.0 escopo `youtube.upload`; ~1.600 unidades de quota por upload (10.000/dia no default ≈ 6 uploads/dia).
- **Posts de Comunidade não têm API** → kit manual (Doc 14: MANUAL/EXPORT).

### Kwai
- Confirmado em 2026-10-01: **não há API pública oficial de publicação** (só Kwai Ads para anunciantes e APIs de terceiros somente-leitura).
- Fluxo URDIA: export gera `platform_variants/kwai/MANUAL_POSTING.md` com texto, mídias, hashtags, rastreabilidade e passos; humano publica no app/Creator Center e confirma no sistema (`POST /api/v1/publications/{id}/confirm`), que move PENDING → PUBLISHED.

## Regras permanentes (independem da rede)

1. **Nada é publicado sem aprovação humana** (Emenda 007: confirm; automation_level 2).
2. O gate do publisher (`publisher_gate`) roda antes de qualquer export/publish.
3. Mudar o plano de plataforma invalida o QC anterior (Doc 14) — novo QC antes de exportar.
4. Tokens/credenciais ficam só no backend, por referência opaca (Doc 14/08).
5. Troca de provider/adaptador exige benchmark + regression + registro em `docs/PROVIDERS.md` (Doc 17 §9/§15).

## Estado de implementação (revisado em 2026-10-19)

- **Instagram: PRIMEIRO ADAPTER AO VIVO** — `packages/providers/instagram.py`
  (photo + carousel via 2-step container/publish), token long-lived no `.env`
  (renovável via `ig_refresh_token`; expiração anotada em
  `META_INSTAGRAM_TOKEN_EXPIRES_AT`). Rota humana:
  `POST /api/v1/publications/{id}/publish` com `public_image_urls`
  (o Instagram baixa a imagem de uma URL pública — arquivos locais não
  servem; sem URL pública, o kit manual segue disponível).
  Se `public_image_urls` for omitido, a rota tenta hospedar imagens do export
  com `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` e `SUPABASE_BUCKET`; a chave permanece
  somente no backend. Hospedar os arquivos os torna públicos: revisar direitos
  e conteúdo antes dessa ação.
- **TikTok implementado, ativação condicionada** — `packages/providers/tiktok.py`
  e `apps/api/tiktok_routes.py`. A publicação passa a `PROCESSING`; só a consulta
  de status após conclusão confirma `PUBLISHED`. OAuth e testes simulados não
  comprovam auditoria aprovada nem publicação pública real.
- **Facebook, X, Threads e upload YouTube**: capacidades declaradas; a rota
  atual recusa publicação por falta de adaptador ao vivo. Credenciais sozinhas
  não concluem essas integrações. YouTube Community e Kwai seguem via kit manual.
- Testes em `tests/test_instagram_publisher.py` simulam HTTP; cobrem foto,
  carrossel, validação, erros, renovação/revogação e a rota (esta depende de DB).
  O teste de revogação de falha de rede não comprova revogação real de token.

## Operação: aprovação e primeira postagem

Siga o roteiro de [primeira publicação no README](../README.md#primeira-publicação-no-instagram).
O export aplica o `publisher_gate`; use o fluxo normal de QC/aprovação/export
para obter uma publicação `PENDING`. A rota de publicação utiliza esse registro
existente; não deve ser interpretada como uma nova execução de todos os gates.

- **API Instagram**: ação humana em `/api/v1/publications/{id}/publish`, com
  `workspace_id`, sessão, `profile_id` e imagens públicas; sucesso registra
  `PUBLISHED`, `remote_id` e auditoria `PUBLICATION_API_PUBLISHED`.
- **Manual**: publicar o kit externamente e então usar
  `/api/v1/publications/{id}/confirm?workspace_id=<uuid>` com corpo JSON `{}` ou
  `{"remote_id":"<id remoto>"}`. Só aceita método `EXPORT`/`MANUAL` em `PENDING`.
- Verifique conta e estado remoto antes de repetir uma requisição que falhou;
  o parâmetro local `idempotency_key` não é enviado à Meta pelo adaptador.
- Cadastro e login URDIA não conectam uma conta social. Não remova o bloqueio
  de autorregistro em produção para viabilizar postagem.

## Fontes (consultadas em 2026-10-01)

- [Meta — Content Publishing (Instagram)](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- [Meta — Threads Publishing](https://developers.facebook.com/documentation/threads/reference/publishing)
- [X — Pricing (pay-per-use)](https://docs.x.com/x-api/getting-started/pricing)
- [TikTok — Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content)
- [TikTok — Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [YouTube — Upload a Video (Data API v3)](https://developers.google.com/youtube/v3/guides/uploading_a_video)
- [SocialCrawl — Kwai (sem API pública)](https://www.socialcrawl.dev/platforms/kwai)
