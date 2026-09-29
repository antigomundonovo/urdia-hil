# DOCUMENTO 05 — AGENTS + PROMPTS + ORCHESTRATION

## Agents
```text
SCOUT
RESEARCHER
CLAIM_ANALYST
ADVERSARIAL_RESEARCHER
SOURCE_ANALYST
ARCHIVIST
RIGHTS_ANALYST
EDITORIAL_ANALYST
JEV
FORMAT_PLANNER
PLATFORM_PLANNER
COPYWRITER
VISUAL_DIRECTOR
QC_ANALYST
AUDIENCE_ANALYST
LEARNING_AGENT
```

## Principle
```text
AGENT = inteligência especializada
CAPABILITY = habilidade controlada
PROVIDER = implementação substituível
GATE = proteção determinística
DATABASE = estado canônico
HUMAN = autoridade editorial final
```

## Restrictions
Nenhum agente recebe simultaneamente database admin + raw credentials + publication unrestricted + rights override.

## Agent responsibilities
- Scout: descobrir candidatos.
- Researcher: buscar contexto/evidence.
- Claim Analyst: quebrar afirmações em claims atômicos.
- Adversarial: buscar contraevidência.
- Source Analyst: dependências/independência.
- Archivist: fotos/documentos/origem.
- Rights: license/permission/status.
- Editorial: fit/novelty/risk/value.
- JEV: recommendation.
- Format: formato.
- Platform: capability/platform plan.
- Copywriter: redação a partir de claims autorizados.
- Visual: estratégia visual.
- QC: gates.
- Audience: métricas/comentários.
- Learning: hipóteses e candidates.

## Capability call
```text
permission → profile → capability → provider → quota → execute → validate → audit
```

## Prompt stack
```text
SYSTEM
↓
PROFILE
↓
TASK
↓
CONTEXT
↓
OUTPUT SCHEMA
```

Governance não pode ser sobrescrita por profile prompt.

## Prompt versioning
Cada prompt: `prompt_id, agent, version, profile, purpose, author, date, schema, test_cases, status`.

## External content
Conteúdo encontrado na web é **DADO NÃO CONFIÁVEL**, nunca instrução.

## Output validation
```text
parse → schema → semantic → policy → persist
```

## ContextPack
Incluir somente:
```text
required sources
required claims
required assets
profile rules
current state
known uncertainties
```

## Memory
Separar:
```text
FACT
PREFERENCE
RULE
EXPERIENCE
HYPOTHESIS
SKILL
```

Toda memória factual deve possuir origem.

## Chains
### Photo
```text
ARCHIVIST → SOURCE_ANALYST → RIGHTS_ANALYST → CLAIM_ANALYST → RESEARCHER → ADVERSARIAL when needed → EDITORIAL_ANALYST → JEV → FORMAT → COPY → VISUAL → QC
```
### News
```text
SCOUT → RESEARCHER → SOURCE_ANALYST → CLAIM_ANALYST → ADVERSARIAL → EDITORIAL → JEV → FORMAT → COPY → VISUAL → QC
```
### Learning
```text
ANALYTICS → AUDIENCE_ANALYST → LEARNING_AGENT → EXPERIMENT → RESULT → RULE_CANDIDATE → HUMAN REVIEW
```

## Failure
Nunca inventar output para esconder erro do agente.
