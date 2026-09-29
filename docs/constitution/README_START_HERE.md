# URDIA — HISTORY INTELLIGENCE LAYER
## PACOTE OFICIAL DE IMPLEMENTAÇÃO

Este pacote contém a Constituição do produto e as especificações necessárias para um Code Agent construir a aplicação HIL para o Antigo Mundo Novo.

### Ordem de leitura
1. `00_HIL_MASTER_CONSTITUTION_V1.0.md`
2. `01_REPOSITORY_ARCHITECTURE.md`
3. `02_DATABASE_CONTRACTS_APIS.md`
4. `03_WORKFLOWS_JOBS_STATES_ACCEPTANCE.md`
5. `04_DATABASE_IMPLEMENTATION.md`
6. `05_AGENTS_PROMPTS_ORCHESTRATION.md`
7. `06_FRONTEND_UI.md`
8. `07_RUNTIME_INSTALLATION_OPERATIONS.md`
9. `08_SECURITY_INTEGRATION_BOUNDARIES.md`
10. `09_RESEARCH_DISCOVERY.md`
11. `10_PHOTO_VISUAL_INTELLIGENCE.md`
12. `11_RIGHTS_PROVENANCE.md`
13. `12_EDITORIAL_OPPORTUNITY.md`
14. `13_CONTENT_RENDERING.md`
15. `14_PLATFORM_ADAPTERS.md`
16. `15_ANALYTICS_COMMENTS_LEARNING.md`
17. `16_TESTS_BENCHMARKS_REGRESSION.md`
18. `17_CODE_AGENT_MASTER_EXECUTION.md`

### Regra de autoridade
O Documento 00 é a fonte de verdade do produto e da arquitetura. Os demais transformam essa constituição em implementação.

Quando houver contradição:
```text
NÃO INVENTAR
↓
IDENTIFICAR A CONTRADIÇÃO
↓
REGISTRAR AMENDMENT REQUIRED
↓
NÃO ALTERAR A CONSTITUIÇÃO SILENCIOSAMENTE
```

### Objetivo da primeira entrega
```text
FOTO HISTÓRICA
↓
ORIGEM
↓
DIREITOS
↓
CLAIMS
↓
EVIDÊNCIA
↓
STORY
↓
OPPORTUNITY
↓
FORMATO
↓
POST / CAROUSEL / MICROLOOP
↓
QC
↓
HUMAN REVIEW
↓
EXPORT
```

### Segurança obrigatória
Aplicar desde a primeira linha:
- menor privilégio;
- isolamento por workspace/profile;
- fail-closed para autorização, rights e publicação;
- secrets fora do código, prompts, logs e frontend;
- validação de schema + validação semântica + policy;
- proteção contra prompt injection, SSRF, path traversal, command injection e SQL injection;
- audit trail append-only na aplicação;
- checkpoints/recovery de jobs;
- fallback sem perda de evidência;
- dependências avaliadas por licença e segurança;
- testes de isolamento e de bypass no CI.
