# DOCUMENTO 11 — RIGHTS + PROVENANCE ENGINE

## Objetivo
Separar autenticidade/identidade histórica de autorização de uso.

## Classes
```text
PUBLIC_DOMAIN
CC0
CC_BY
CC_BY_SA
OTHER_FREE_LICENSE
PERMISSION_REQUIRED
UNKNOWN
PROHIBITED
```

## Workflow
```text
asset
→ origin
→ custodian
→ license/permission lookup
→ evidence
→ classification
→ verification
→ publishable / blocked
```

## Negative assumption
Não encontrar restrição não significa domínio público.

## Rights evidence
Persistir asset, source, statement, URL, retrieval, verifier, territory, commercial use, modification, attribution e notes.

## Permission required
Persistir quem autorizou, escopo, território, duração, mídia e evidence da permissão.

## Derived assets
Nunca apagar a history do original. Rights do derivado precisam estar ligados ao fundamento do original + transformação.

## C2PA
Pode registrar cadeia de criação/modificação. Não é prova isolada de autenticidade histórica.

## Publication snapshot
Na aprovação registrar assets, rights, source/evidence, license state e verification timestamp.

## Gate
```text
UNKNOWN → BLOCK
PROHIBITED → BLOCK
REQUIRES_PERMISSION → BLOCK
VERIFIED → MAY_PROCEED
```

## Revalidation
Mudança relevante na página/licença/origem gera `REVIEW_REQUIRED`.

## User-provided assets
Upload do usuário não prova domínio público.

## Override
Qualquer override futuro exige permission elevada + reason + actor + audit.

## Done
Origin, license evidence, classification, verification e gate estão persistidos.
