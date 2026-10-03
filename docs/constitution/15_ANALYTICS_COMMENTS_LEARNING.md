# DOCUMENTO 15 — ANALYTICS + COMMENTS + LEARNING

## Normalized metrics
```text
REACH
IMPRESSIONS
VIEWS
SAVES
SHARES
COMMENTS
CLICKS
FOLLOWERS_GAINED
RETENTION
REPLAYS
RESPONSES
PARTICIPATION
CONVERSION
```

## Event model
Não sobrescrever histórico. Cada coleta gera novo `metric_event`.

## Qualified learning signals
```text
SOURCE_REQUEST
CORRECTION
DOCUMENT_SUBMISSION
TESTIMONY
RECURRING_QUESTION
CONTINUATION_REQUEST
AUDIENCE_DISCOVERY
```

## Comments pipeline
```text
collect → language → spam → intent → entities → cluster → qualified signal → opportunity
```

## Testimony
Classificar `POSSIBLE_ORAL_HISTORY`. Não é confirmação automática.

## Competitor learning
Observar topic, format, hook, visual, frequency, comments, series, timing e observable engagement. Evitar inferir causalidade simples.

## Experiment model
```text
experiment_id
hypothesis
control
variant
platform
sample
metrics
confounders
result
confidence
decision
```

Exemplos: 5 vs 8 slides; pergunta vs afirmação; CTA vs sem CTA; 7s vs 10s.

## No single metric
Nunca otimizar só por views. Contextualizar reach, saves, shares, comments, followers, retention e qualified signals.

## Learning pipeline
```text
DATA → EXPERIENCE → HYPOTHESIS → EXPERIMENT → RESULT → RULE_CANDIDATE → HUMAN REVIEW → ACTIVE_RULE
```

## Profile learning
Private learning permanece no profile. Shared learning exige generalização, remoção de identificadores, privacy review e aprovação.
Metrics, comments, experiments e rules devem validar o workspace/profile do
registro contra o contexto da operação; IDs de outro profile não autorizam
leitura, escrita, revisão ou ativação.

## Corrections
```text
ERROR DETECTED → CLAIM REVIEW → SOURCE REVIEW → SEVERITY → DECISION → LEARNING
```

Não apagar histórico.

## Audience memory
Guardar apenas o necessário, dentro do scope do profile.

## MiroFish
Somente lab; simulação não é truth nem previsão garantida.
