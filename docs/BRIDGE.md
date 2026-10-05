# PONTE STUDIO⇄HIL — especificação de consumo (V2.1, Emenda 002)

> Para a IA/operador do **URDIA Studio** (`C:\Antigomundonovo`).
> O HIL expõe **leitura somente** da demanda da audiência. Nada mais.

## Pré-requisitos

1. O operador humano cria uma chave no painel HIL (página **Social**,
   cartão "Ponte Studio") e a entrega ao Studio. A chave aparece **uma
   única vez**; formato `urdia_mk_<48 hex>`.
2. A chave é escopada a UM workspace: só lê dados daquele workspace.

## Autenticação

Todas as chamadas de máquina usam header:

```text
Authorization: Bearer urdia_mk_…
```

Não há cookie de sessão. A chave NÃO autentica nenhuma outra rota da API
(allowlist = o router `/api/v1/bridge`).

## Endpoints (allowlist completa)

### GET /api/v1/bridge/demand?workspace_id=<uuid>[&profile_id=<uuid>]

Retorna a lista de demandas estruturadas da audiência (contrato §10),
mais recentes primeiro:

```json
[
  {
    "id": "…",
    "profile_id": "… | null",
    "summary": "Demanda recorrente por conteúdo sobre X",
    "evidence": { … } | null,
    "unique_people_count": 7,
    "growth": 0.12,
    "engagement": 0.34,
    "platforms": ["instagram"],
    "confidence": 0.8,
    "editorial_fit": 0.9,
    "created_at": "2026-10-05T…"
  }
]
```

Erros: `401` chave ausente/inválida/revogada · `404` workspace de outra
chave (nunca revela existência).

### GET /api/v1/bridge/clients?workspace_id=<uuid> — SOMENTE SESSÃO HUMANA

Gestão de chaves (criar via `POST /api/v1/bridge/clients`, revogar via
`DELETE /api/v1/bridge/clients/{id}?workspace_id=…`) exige login humano
no painel. A chave de máquina não acessa essas rotas.

## Regras de ouro (contrato + emendas)

1. **Leitura somente.** Não existe endpoint de escrita na ponte.
2. Toda decisão editorial continua **humana** (Emenda 007). Demanda alta
   não autoriza nada automaticamente — é insumo.
3. O HIL não entra no pipeline de vídeo; o Studio não vira social inbox.
4. Uso da chave gera evento de auditoria no HIL (`last_used_at` +
   `AuditEvent` de criação/revogação).
5. Se a chave vazar: revogar no painel (efeito imediato) e criar outra.
