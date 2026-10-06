# Music Intelligence & Music Trend Intelligence — HIL (Emenda 014)

> Implementação no HIL da arquitetura de referência "MusicIntelligence"
> (2026-10-06), adaptada ao foco em postagens. HIL hoje = futuro
> URDIA Social (mesmo projeto — Emenda 014). Fonte dos requisitos:
> prompt-mestre do dono + docs/amendments/AMENDMENT-2026-10-06-014.md.

## Princípios invioláveis

| Princípio | Onde é garantido |
|---|---|
| TREND SIGNAL ≠ LICENSE | `MusicTrendSignal.rights_state` nasce UNKNOWN sempre; adapter nunca atribui licença |
| UNKNOWN/BLOCKED não publicável | `CatalogMusicProvider.validate_usage` (fail-closed) + revalidação no export |
| Não inventar música/direito/sinal | catálogo só com proveniência (`license_notes`); fontes sem API = UNAVAILABLE |
| Portão humano (Emenda 007) | `audio_plans.status` SUGGESTED→APPROVED/REJECTED só por rota autenticada |
| Idioma ≠ plataforma | `packages/multilingual`; `music_language_code` ≠ idioma do conteúdo |
| SOURCE ≠ TARGET | colunas `source_*`/`target_*` em packages/publications |
| Música ≠ MP3 | `MusicTrack` é entidade rastreável (dna, licença, hash); arquivo é só representação |

## Componentes

### 1. Catálogo de músicas — `music_tracks` (packages/domain/audio.py)
Campos: título, artista, duração, mood, BPM, instrumental, **music_language_code/
music_locale_code** (idioma da letra), licença (`license_type` + notes +
expiração + plataformas/territórios permitidos + atribuição), **MusicDNA**
(JSONB), arquivo (storage_path + hash) e **rights_state**.

**MusicDNA** (contrato: packages/contracts/music.py): genre, subgenre, bpm,
energy, tension, rhythmic_density, instrumentation, texture, vocal_mode,
idioma musical, estrutura (intro/build/climax/release/silêncios), duração,
narrative_role... — campos ausentes = desconhecidos, **nunca inventados**.
Correlação cross-platform usa `MusicDNA.fingerprint()` (gênero + faixa de
BPM + faixa de energia + vocal_mode), nunca nome de música.

**Estados de direitos** (referência §7): `ORIGINAL`, `LICENSED`,
`PLATFORM_LIMITED` (só nas plataformas declaradas), `UNKNOWN`, `BLOCKED`.
Sem prova de licença, track nasce UNKNOWN. `validate_usage` devolve códigos
explícitos: MUSIC_RIGHTS_UNKNOWN, MUSIC_RIGHTS_BLOCKED,
MUSIC_PLATFORM_SCOPE_MISMATCH, MUSIC_LICENSE_EXPIRED,
MUSIC_TERRITORY_NOT_ALLOWED.

### 2. Plano de áudio — `audio_plans` + packages/research/audio.py
`AudioService.recommend_plan` (determinístico, explicável): regras editoriais
por palavra-chave → mood/intensidade; seleção fail-closed no catálogo
(mood → intensidade → instrumental → recente); instrumental não é limitado
por idioma; vocal em idioma diferente do conteúdo não é escolhido sem
decisão editorial. Sem candidato → plano NONE (conteúdo funciona sem
música). Decisão humana (`decide_plan`) grava auditoria AUDIO_PLAN_DECIDED.

### 3. Export e publicação (packages/research/content.py)
- Com plano APROVED: trilha revalidada no momento do export (auditoria
  MUSIC_RIGHTS_VALIDATED/BLOCKED) e copiada para o kit manual
  (`audio/` + seção no MANUAL_POSTING.md com trecho, volume, fades,
  obrigação de créditos).
- APIs do TikTok/Instagram não anexam trilha no upload → a publicação
  registra `audio_applied=false` + motivo (PLATFORM_API_NOT_SUPPORTED).
  Nunca fingir que a música foi aplicada.

### 4. Trend Intelligence — music_trend_signals + packages/research/music_trends.py
- **Adapters por plataforma** (packages/providers/trend_sources.py):
  **YouTube real** (YouTube Data API v3, chart=mostPopular categoria música;
  liga com `YOUTUBE_API_KEY` no .env; região `YOUTUBE_TREND_REGION`, default BR).
  TikTok/Instagram/Facebook/Kwai = `TREND_SOURCE_UNAVAILABLE` honesto até
  existir API oficial com credencial (decisão humana). Nunca scraping frágil.
- **TrendSignal** (contracts/music.py): componentes SEPARADOS — popularity,
  velocity, acceleration, persistence, saturation, cross_platform_spread,
  fits, rights_usability, confidence, freshness. Proibido score único opaco.
- **Estados explicáveis**: HUGE_SATURATED, EMERGING, DECAYING,
  CROSS_PLATFORM, PLATFORM_LOCAL, RIGHTS_BLOCKED... cada estado vem com
  lista de razões (`derive_state`).
- **Freshness**: TTL por fonte; sinal vencido = `stale`, nunca tratado
  como atual.
- **Correlação cross-platform**: agrupamento por fingerprint do DNA em ≥2
  plataformas.

### 5. Integração com o Studio (futura)
`StudioMusicGateway` (packages/providers/music.py) é o contrato para
consumir MusicPlan/MusicAsset do Studio. Hoje responde
`STUDIO_GATEWAY_UNAVAILABLE` — quando o Studio expor a API, implementa-se
o cliente sem tocar no resto. O Social/HIL NÃO gera música.

## Operação no painel
- **/audio**: registrar trilha (com prova de licença), ver selo de direitos,
  bloquear/desbloquear, buscar tendências por plataforma.
- **Cartão "Trilha sonora"** na oportunidade: 1. Sugerir → 2. Aprovar /
  3. Rejeitar (motivo opcional) — sempre com o "Por quê" da sugestão.

## APIs (autenticadas por sessão humana; todas sob /api/v1/audio)
```
GET  /tracks                      lista o catálogo
POST /tracks                      registra track (rights fail-closed)
POST /tracks/{id}/status          muda rights_state (bloquear etc.)
POST /packages/{id}/suggest       gera sugestão determinística
GET  /packages/{id}/plan          último plano
POST /plans/{id}/decision         PORTÃO HUMANO (APPROVED/REJECTED)
POST /trends/ingest               ingesta de 1 plataforma (UNAVAILABLE honesto)
```

## Testes
- `tests/test_multilingual.py` (31) — contrato de idioma.
- `tests/test_language_propagation.py` (11) — propagação fim a fim.
- `tests/test_audio.py` (16) — catálogo, direitos fail-closed, portão.
- `tests/test_music_trends.py` (23) — segurança lógica (§57), YouTube
  adapter, ingestão, correlação por DNA, freshness.
