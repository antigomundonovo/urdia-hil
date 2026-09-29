# DOCUMENTO 03 — WORKFLOWS + JOBS + STATES + ACCEPTANCE

## State machine
```text
DISCOVERED → NORMALIZED → CLUSTERED → CANDIDATE → RESEARCHING → EVIDENCE_COLLECTED → FACT_CHECK → UNCERTAINTY_REVIEW → OPPORTUNITY_SCORED → FORMAT_SELECTED → PLATFORM_SELECTED → DRAFTING → VISUAL_PRODUCTION → RIGHTS_CHECK → SEO_CHECK → QUALITY_CONTROL → HUMAN_REVIEW → READY → SCHEDULED → PUBLISHED → ANALYZING → LEARNING
```
Auxiliares: `QUARANTINED BLOCKED NEEDS_RESEARCH RIGHTS_BLOCKED FACT_CHECK_FAILED DUPLICATE REJECTED CANCELLED`.

## Transition Service
Toda transição verifica:
```text
current state
transition rule
gate status
permission
required data
audit
```

## Jobs
```text
DISCOVERY_SCAN
SOURCE_RETRIEVAL
SOURCE_EXTRACTION
SOURCE_CLUSTERING
IMAGE_ANALYSIS
IMAGE_RESEARCH
RIGHTS_RESEARCH
CLAIM_EXTRACTION
CLAIM_VERIFICATION
ADVERSARIAL_RESEARCH
OPPORTUNITY_ANALYSIS
FORMAT_PLANNING
CONTENT_GENERATION
VISUAL_GENERATION
QC
EXPORT
PUBLICATION
ANALYTICS_SYNC
COMMENT_SYNC
LEARNING_ANALYSIS
```

## Checkpoint
```json
{"completed_steps":["fetch","extract","normalize"],"next_step":"cluster"}
```

## Retryable
Timeout, temporary network, provider unavailable, rate limit, temporary service.

Não retry infinito para invalid schema, bad credentials, rights block, policy block ou fact-check failure.

## Quality Gates
```text
RELEVANCE
EVIDENCE
FACTUALITY
UNCERTAINTY
RIGHTS
ORIGINALITY
VISUAL
SEO
PLATFORM
ANTI-SLOP
HUMAN_REVIEW
```

## Acceptance Tests
- claim sem evidence → `NOT_READY`;
- rights unknown → `RIGHTS_BLOCKED`;
- sources conflitantes → `CONTROVERSIAL`;
- copy → `REQUIRES_TRANSFORMATION`;
- imagem duplicada → `DUPLICATE_CANDIDATE`;
- Profile B não acessa A;
- provider failure → fallback preservando contrato;
- platform failure → manual export;
- restart → recovery por checkpoint;
- correction → histórico preservado.

## Vertical slices
1. Foto histórica → Post.
2. Notícia → História.
3. Comentário → Pauta.
4. Concorrente → Nova oportunidade.
5. Post → Learning.

## Definition of Done
```text
abrir → pesquisar → encontrar → agrupar → investigar → provar → preservar incerteza → opportunity → produzir → rights → QC → human review → export → medir
```
