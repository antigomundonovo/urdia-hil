# DOCUMENTO 06 — FRONTEND / UI IMPLEMENTATION

## Stack
```text
React
TypeScript
Vite
Tailwind
React Router
TanStack Query
Zod
```

## Navigation
```text
Dashboard
Radar
  Mundo
  Brasil
  Tendências
  Concorrentes
  Comentários
Oportunidades
  Novas
  Prioritárias
  Quarentena
  Arquivo
Pesquisa
  Investigações
  Fontes
  Claims
  Evidências
  Story Graph
Produção
  Imagem
  Carrossel
  Microloop
  Interativo
  Especial
Calendário
Publicação
Analytics
Learning
Assets
Sources
Experiments
Settings
```

## Dashboard
Responder:
```text
O que está acontecendo?
O que merece atenção?
O que vale publicar?
O que está pronto?
O que está bloqueado?
O que falhou?
Como o sistema está?
```

## Opportunity detail
```text
HEADER
WHY
STORY
CLAIMS
EVIDENCE
UNCERTAINTIES
ASSETS
RIGHTS
FORMAT
PLATFORMS
DRAFT
QC
DECISION
AUDIT
```

## Why Panel
```text
Por que agora?
Por que ANM?
Por que este formato?
Por que esta plataforma?
Quais fontes?
Quais evidências?
Quais riscos?
O que falta?
Por que não publicar?
```

## Production
Editor para:
```text
title
caption
slides
CTA
SEO
hashtags
assets
platform variants
```

Claims/evidence permanecem rastreáveis e não são tratados como texto sem origem.

## Carousel editor
Slide list + canvas + assets + evidence + preview.

## Microloop editor
```text
image
text
duration 5/7/10/12s
minimal motion
audio
preview
```

Não construir voice-over ou editor audiovisual complexo na V1.

## QC UI
Cada gate mostra `PASS / WARNING / FAIL` com razão. Não existir “ignore gate”.
No editor, a pessoa seleciona explicitamente quais claims sustentadas aparecem
no rascunho. QC válido é requisito para aprovação; qualquer mudança posterior
exige novo QC e nova aprovação. A exportação para publicação manual só fica
disponível após a aprovação; publicação direta depende de adapter configurado.

## Human Review
Ações:
```text
APPROVE
EDIT
REJECT
QUARANTINE
REQUEST RESEARCH
REQUEST REWRITE
CHANGE FORMAT
CHANGE PLATFORM
CHANGE TIME
```

## Jobs
Mostrar status, progresso, step, provider, attempts, duration, checkpoint e erro.

## Governance
Provider, capability, health, quota, fallback, version, license e last verified.

## UX/security
Frontend não é security boundary. Toda autorização é revalidada no backend. Não confiar no `profile_id` fornecido pelo browser.

Implementar keyboard navigation, focus, labels semânticos, contraste e alt text.

## E2E principal
```text
open → select ANM → opportunity → evidence → rights → draft → QC → approve → export
```
