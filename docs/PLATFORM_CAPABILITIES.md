# Matriz de Capacidades de Plataformas (2026-10-01)

> Complemento operacional do Doc 14 (lista oficial: AMENDMENT-2026-10-01-011).
> Política do dono: **rede com API oficial → publica direto da URDIA, sempre
> APÓS aprovação humana (confirm)**; rede sem API → o export gera um **kit de
> postagem manual completo** (texto, mídias, hashtags, passos) e a publicação
> é confirmada no sistema depois de feita à mão.
> Nenhum adapter está habilitado hoje — integração real só após credenciais
> oficiais + validação + teste de revogação (Doc 14).

## Resumo

| Plataforma | Método-alvo | API oficial de publicação | Bloqueio atual |
|---|---|---|---|
| Instagram | **API — ADAPTER ATIVO** 🟢 | ✅ graph.instagram.com (photo/carousel) | credenciais OK (URDIA-Media - IG); publicação exige imagem em **URL pública** |
| Facebook | **API** | ✅ Graph API (páginas) | credenciais (app Meta + permissões de página) |
| X (Twitter) | **API** | ✅ API v2 (pay-per-use) | conta de dev + créditos (~US$ 0,015/post; US$ 0,20 com link) |
| Threads | **API** | ✅ Threads API (2 passos) | credenciais (app Threads OAuth) |
| TikTok | **API** | ✅ Content Posting API | app com escopo `video.publish` **+ auditoria para Direct Post** (sem auditoria o post sai privado) |
| YouTube | **API** (vídeo) | ✅ Data API v3 `videos.insert` | projeto Google Cloud verificado + OAuth `youtube.upload`; quota ~6 uploads/dia |
| YouTube Community | **MANUAL** | ❌ sem API para posts de comunidade | — (kit manual no export) |
| Kwai | **MANUAL** | ❌ não existe API oficial de publicação (apenas Ads e leituras não-oficiais) | — (kit manual no export) |

## Detalhes e limites por rede

### Instagram
- Fluxo: criar media container → `media_publish`. Carrossel conta como 1 post.
- Limite: 100 posts publicados via API por janela móvel de 24h.
- Requisitos: conta Business/Creator + página do Facebook vinculada + app Meta tipo Business.

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

## Estado de implementação (2026-10-02)

- **Instagram: PRIMEIRO ADAPTER AO VIVO** — `packages/providers/instagram.py`
  (photo + carousel via 2-step container/publish), token long-lived no `.env`
  (renovável via `ig_refresh_token`; expiração anotada em
  `META_INSTAGRAM_TOKEN_EXPIRES_AT`). Rota humana:
  `POST /api/v1/publications/{id}/publish` com `public_image_urls`
  (o Instagram baixa a imagem de uma URL pública — arquivos locais não
  servem; sem URL pública, o kit manual segue disponível).

## Fontes (consultadas em 2026-10-01)

- [Meta — Content Publishing (Instagram)](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- [Meta — Threads Publishing](https://developers.facebook.com/documentation/threads/reference/publishing)
- [X — Pricing (pay-per-use)](https://docs.x.com/x-api/getting-started/pricing)
- [TikTok — Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content)
- [TikTok — Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [YouTube — Upload a Video (Data API v3)](https://developers.google.com/youtube/v3/guides/uploading_a_video)
- [SocialCrawl — Kwai (sem API pública)](https://www.socialcrawl.dev/platforms/kwai)
