# DOCUMENTO 14 — PLATFORM ADAPTER SPECIFICATION

## Principle
Plataformas são adapters substituíveis. O core não conhece limits rígidos de uma plataforma.

## Adapter contract
Cada adapter declara:
```text
platform
capabilities
publication_method
requirements
limits
quota
analytics
last_verified
status
```

O contrato provider-neutral e o registry explícito ficam em
`packages/providers/platforms.py`. Nenhum adapter de plataforma é habilitado
por padrão: só registrar integrações após configurar credenciais oficiais,
validar requisitos/limites documentados e testar revogação de conta. Tokens
permanecem no backend; o core passa apenas referências opacas de credenciais.

## Platforms
```text
Instagram
Facebook
X (Twitter)
YouTube Community
TikTok
Threads
Kwai
```

> Lista definitiva conforme AMENDMENT-2026-10-01-011 (APROVADA):
> Pinterest, LinkedIn e Reddit saem do escopo do projeto.

## Methods
```text
API
MANUAL
EXPORT
UNAVAILABLE
```

## Capability Registry
Nunca codificar `MAX = ...` no core. Consultar registry/runtime capability.

## YouTube Community
Suportar `MANUAL`/`EXPORT` até que capability oficial adequada esteja realmente configurada.

## Kwai
Mesma regra do YouTube Community: suportar `MANUAL`/`EXPORT` até que uma
capability oficial adequada esteja realmente configurada
(AMENDMENT-2026-10-01-011).

## Publication security
Publisher recebe somente:
```text
READY
APPROVED
RIGHTS_VERIFIED
PLATFORM_ALLOWED
```

Além desses quatro gates, a publicação exige QC aprovado para o estado atual
do pacote. Alterações em rascunho, claims/evidências, direitos ou plano de
plataforma invalidam a avaliação anterior e exigem nova execução do QC antes
de aprovar ou exportar.

## Idempotency
Quando disponível, usar chave baseada em profile + content + platform + version para evitar duplicate publish.

## Error normalization
```text
AUTH_ERROR
RATE_LIMIT
POLICY_BLOCKED
INVALID_PAYLOAD
SERVER_ERROR
NETWORK_ERROR
UNAVAILABLE
```

## Retry/fallback
```text
retry → fallback → manual export
```

## Authentication
OAuth/tokens somente no backend/provider layer.

## Capability change
Mudança de docs/runtime → `REVALIDATION_REQUIRED`.

## No lock-in
Criação/exportação não depende de nenhuma plataforma específica.

## Done
Capability registrada, autenticação, validação, teste, publicação quando aplicável, remote ID, analytics e fallback.
