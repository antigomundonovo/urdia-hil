# CONTRATO_TECNOLOGICO_URDIA
## Mapa técnico entre URDIA Studio, URDIA-HIL e Core compartilhado

**Versão:** 1.0  
**Data:** 2026-10-02  
**Finalidade:** manter as duas linhas de desenvolvimento alinhadas sem duplicar trabalho.

---

# 1. Regra principal

O URDIA possui duas frentes complementares:

- **URDIA Studio:** produção, edição, revisão e publicação de **vídeos**.
- **URDIA-HIL:** redes sociais, comentários, audiência, demanda, feedback e inteligência social.

Não transformar o Studio em uma plataforma de Social Inbox.
Não transformar o HIL em uma cópia do Studio.

A integração futura deve acontecer por:

- contratos;
- interfaces;
- eventos;
- APIs;
- objetos de domínio;
- registros de auditoria;
- capability/provider registries;
- ExecutionContext.

A regra é:

> **compartilhar arquitetura e contratos quando isso reduz duplicação; manter separados os componentes que pertencem ao domínio de cada produto.**

---

# 2. URDIA Studio

## Missão

Pipeline completo de vídeo:

`Tema → Pesquisa → Roteiro → Storyboard → Assets → Voz → Edição → Inspeção → Review → SEO → Calendário → Publicação`

### Plataformas oficiais do pipeline de vídeo

- Instagram
- Facebook
- YouTube
- TikTok
- Kwai

**X e Threads NÃO fazem parte do pipeline de vídeo do URDIA Studio.**

---

# 3. URDIA-HIL

## Missão

Camada especializada em:

- comentários;
- Social Inbox;
- classificação;
- sugestões de resposta;
- histórico de autores por plataforma;
- demanda da audiência;
- oportunidades;
- feedback;
- Audience Pulse;
- Response Debt;
- clusters de demanda;
- factuality challenges originados por comentários;
- integração social com o Studio.

Fluxo principal:

`Audiência → Comentários → Triage → Demanda → URDIA Studio/HIL → Conteúdo → Publicação → Feedback`

O HIL não deve assumir o pipeline de renderização de vídeo como sua responsabilidade principal.

---

# 4. Core compartilhado

Componentes que podem ser compartilhados entre Studio e HIL, preferencialmente por contratos/interfaces:

- ExecutionContext
- Workspace
- Profile
- Authentication/session
- Membership
- Governance
- Audit Ledger
- Capability Registry
- Provider Registry
- Evidence/Provenance
- Factuality
- Research contracts
- Judge/System 2 contract
- Jobs/Worker
- Idempotency
- Contracts/API boundaries
- Event model
- Security boundaries
- PII/privacy primitives

O objetivo é evitar dois sistemas fazendo a mesma coisa de maneiras incompatíveis.

---

# 5. Inventário tecnológico conhecido

| Tecnologia / componente | Finalidade | Dono principal | HIL pode reutilizar? | Regra |
|---|---|---|---|---|
| Python | Backend, automação e serviços | Studio/Core | Sim | Reutilizar quando fizer sentido |
| FastAPI | API/orquestração HTTP | Studio/Core | Sim | Não duplicar conceitos sem necessidade |
| React | Interface | Studio | Sim | HIL pode ter sua própria UI |
| TypeScript | Frontend | Studio | Sim | Compartilhável por padrão de contratos |
| Vite | Build/dev frontend | Studio | Sim | Não é requisito do HIL |
| Tailwind CSS | UI | Studio | Sim | Livre para cada frontend |
| SQLite | Persistência local atual | Studio | Não necessariamente | HIL pode usar outra persistência |
| SQLModel | ORM/modelagem atual | Studio | Não necessariamente | Não impor ao HIL |
| FFmpeg | Renderização/edição de vídeo | Studio | Não como núcleo | Exclusivo do pipeline de vídeo |
| Edge-TTS | Narração | Studio | Não como núcleo | Não transformar HIL em engine de voz |
| Whisper / faster-whisper | Transcrição/alinhamento | Studio | Opcional | Usar somente se uma necessidade real surgir |
| Vision Inspector | Inspeção visual | Studio | Não como núcleo | Específico do pipeline audiovisual |
| AI Routing | Seleção/fallback de modelos | Studio/Core | Sim conceitualmente | Compartilhar contrato/provider pattern |
| OmniRoute | Gateway/roteamento de IA | Studio | Opcional | Não duplicar gateway sem necessidade |
| 9Route | Gateway/roteamento de IA | Studio | Opcional | Mesmo princípio |
| Pollinations.ai | Fallback de geração visual | Studio | Não como dependência social | Só reutilizar se houver caso real |
| Google Gemini fallback | Fallback de IA | Studio | Opcional | Respeitar privacidade/uso |
| Research Reach | Pesquisa/acesso a fontes | Core/Studio | Sim | Forte candidato a serviço compartilhado |
| Judge/System 2 | Avaliação/decisão | Core/Studio | Sim | NÃO criar um segundo Judge |
| ScopeGuard | Limites de escopo/profile/publication | Core/Studio | Sim | Reutilizar conceito/contrato |
| OAuth | Conexões com plataformas | Core/Studio | Sim | HIL pode usar seus próprios conectores |
| SEO Kit | Pacotes de publicação | Studio | Parcial | HIL pode fornecer sinais, Studio monta pacote |
| Calendário | Agendamento de publicação | Studio | Parcial | HIL pode produzir demanda, não substituir calendário |
| Jobs/Workers | Execução assíncrona | Core/Studio | Sim | Assimilar arquitetura de worker do HIL quando superior |
| Git | Versionamento | Ambos | Sim | Cada repo mantém seu próprio histórico |
| GitHub | Repositório/CI/colaboração | Ambos | Sim | Não misturar repositórios |
| Pytest | Testes backend | Ambos | Sim | Manter suites separadas |
| Vite build | Build frontend | Studio | Não obrigatório | Não impor ao HIL |

---

# 6. Tecnologias e referências externas

Estas referências foram analisadas, mas NÃO devem ser tratadas automaticamente como dependências adotadas:

## Agent-Reach

Uso conceitual:
- capability/installer/doctor;
- acesso a fontes;
- provider/backend para Research Reach.

Regra:
- pode ser assimilado como provider;
- não substituir o Research Reach/Research Orchestrator existente sem decisão arquitetural.

## CL4R1T4S / ANTHROPIC

Uso conceitual:
- decomposição de tarefas;
- seleção de ferramentas;
- planner;
- evidências;
- memória/boundaries;
- governança.

Regra:
- usar padrões arquiteturais públicos;
- não copiar prompts;
- não declarar integração oficial com Anthropic.

## YouTube Agentic AI Studio

Padrões úteis:
- Research;
- Script;
- Narration;
- Images;
- Video;
- Review;
- Upload;
- artefatos intermediários;
- human review;
- fallback de modelos;
- render orchestration.

Regra:
- usar padrões;
- não transformar o Studio em produto YouTube-first;
- não adotar stock media como fundamento.

## Supabase / pgvector

Uso potencial:
- persistência social/audience;
- RLS;
- Vault;
- Edge Functions;
- embeddings;
- HNSW/pgvector.

Regra:
- não migrar o Studio inteiro automaticamente;
- HIL pode usar Supabase atrás de sua boundary de persistência;
- Edge Function, quando usada, deve ficar limitada à função definida pelo contrato.

---

# 7. O que foi analisado no URDIA-HIL e vale assimilar no Studio

A análise do HIL encontrou vários componentes/padrões que podem melhorar o Studio.

## 7.1 ExecutionContext

O HIL possui conceito de contexto com:

- workspace_id;
- profile_id;
- actor_id;
- job_id;
- capability;
- correlation_id.

### Assimilação

Transformar isso em referência para um contexto de execução consistente no Core/Studio.

---

## 7.2 Audit Ledger

O HIL possui padrão de auditoria com:

- workspace;
- profile;
- actor;
- action;
- entity;
- state;
- reason;
- rule_version;
- provider;
- evidence;
- metadata.

### Assimilação

Fortalecer o Studio com auditoria estruturada e rastreável.

---

## 7.3 Governance

O HIL possui padrões para:

- transições;
- políticas;
- capabilities;
- aprovação humana.

### Assimilação

Reutilizar os conceitos no Studio, especialmente em:

- publicação;
- aprovação;
- mudanças de estado;
- permissões;
- operações externas.

---

## 7.4 Authentication / Sessions

O HIL possui padrões interessantes:

- sessões opacas;
- digest SHA-256 do token;
- Argon2;
- verificação de e-mail;
- password reset;
- rate limiting;
- membership;
- revogação.

### Assimilação

Usar como referência para endurecer Auth do Studio.

Não copiar cegamente. Adaptar ao contexto web-first.

---

## 7.5 Worker / Jobs

O `apps/worker` do HIL é uma boa referência de arquitetura para:

- jobs;
- execução assíncrona;
- estados;
- retry controlado;
- isolamento de execução.

### Assimilação

Melhorar o worker/job model do Studio.

---

## 7.6 Evidence / Verification

O HIL possui verificação determinística baseada em evidências.

Modelo observado:

- 0 evidências → UNKNOWN
- contradição → CONTROVERSIAL
- >= 2 grupos independentes de suporte → PROBABLE
- exatamente 1 grupo → POSSIBLE
- CONFIRMED/REFUTED não são atribuídos automaticamente.

### Assimilação

É uma boa base para o sistema de factualidade do Studio.

Regra:

> evidência deve ser separada de inferência, hipótese e decisão.

---

## 7.7 Rights / Provenance

O HIL possui preocupação explícita com:

- direitos;
- proveniência;
- rastreabilidade.

### Assimilação

Fortalecer o pipeline de assets do Studio.

Especialmente para:
- imagens;
- áudio;
- fontes;
- geração por IA;
- referências utilizadas;
- publicação.

---

## 7.8 Rendering Infrastructure

O HIL possui uma camada de rendering generalizável.

### Assimilação

A ideia de infraestrutura de rendering pode melhorar a arquitetura do Studio.

Porém:

> o Studio continua sendo o proprietário do rendering audiovisual.

Não importar templates ANM ou identidade histórica.

---

## 7.9 Contracts / API separation

O HIL tem separação explícita entre:

- contracts;
- domain;
- governance;
- providers;
- rendering;
- research;
- shared.

### Assimilação

Essa separação pode melhorar a modularidade do Studio.

---

## 7.10 Provider Registry

O HIL possui arquitetura de providers.

### Assimilação

Convergir conceitualmente com o provider registry já existente no Studio.

Não criar dois registries concorrentes dentro do mesmo produto.

---

## 7.11 Capability Registry

Mesmo princípio.

### Assimilação

Um registry de capabilities consistente ajuda:

- segurança;
- disponibilidade;
- provider selection;
- Connection Doctor;
- capability drift.

---

## 7.12 Profile Architecture

Profile architecture is already domain-neutral; ANM remains only a legacy profile for existing historical workspaces.

Mas a estrutura de Profile é valiosa.

### Assimilação

O Studio deve manter:

`Profile → Editorial Identity → Policies → Prompts/Intelligence`

Nunca:

`URDIA → Antigo Mundo Novo`

---

## 7.13 Research Architecture

Padrão desejável:

`Question → Research → Sources → Evidence → Analysis → Judge → Human Review`

### Assimilação

Isso melhora o fluxo factual do Studio sem importar o domínio social do HIL.

---

# 8. O que NÃO deve ser importado do HIL para o Studio

## Não importar como núcleo:

- History Intelligence Layer como identidade do produto;
- hardcoding de Antigo Mundo Novo;
- ANM como default universal;
- políticas editoriais históricas específicas;
- Inbox social como núcleo;
- Audience Engine como núcleo;
- Demand Engine como núcleo;
- Social Relationship Graph como núcleo;
- resposta automática a comentários;
- lógica de Social Intelligence como pipeline principal;
- X no pipeline de vídeo;
- Threads no pipeline de vídeo;
- quota antiga de YouTube de 1600;
- segundo Research Orchestrator;
- segundo Judge/System 2;
- segundo Auth concorrente;
- segundo Provider Registry concorrente;
- segundo Capability Registry concorrente.

---

# 9. Regra especial sobre plataformas

## Studio

```text
instagram
facebook
youtube
tiktok
kwai
```

Essas são as plataformas oficiais do pipeline de vídeo.

## HIL

O HIL pode possuir capacidades sociais adicionais conforme seus contratos e capacidades reais.

Isso não significa que essas plataformas devam aparecer no catálogo de publicação de vídeo do Studio.

---

# 10. Audience → Studio

A ponte principal deve ser uma demanda estruturada.

Exemplo:

```text
AudienceDemand
    ↓
summary
evidence
unique_people_count
growth
engagement
platforms
confidence
editorial_fit
    ↓
human decision
    ↓
URDIA Studio
    ↓
content production
```

O HIL pode detectar:

> "Há demanda recorrente por conteúdo sobre X."

O HIL NÃO deve automaticamente assumir:

> "Vou criar e publicar o vídeo."

A produção continua pertencendo ao fluxo apropriado do URDIA Studio.

---

# 11. Factuality Challenge

Comentários podem gerar desafios de factualidade.

Fluxo:

```text
Comentário
   ↓
Factuality Challenge
   ↓
Research Reach
   ↓
Evidence
   ↓
Judge/System 2
   ↓
confirmed / disputed / unsupported / unknown
   ↓
Human review
```

Regra:

> comentário não é evidência simplesmente porque foi escrito por uma pessoa.

---

# 12. Princípios de integração

1. Não duplicar serviços.
2. Não copiar um repositório inteiro para o outro.
3. Compartilhar contratos antes de compartilhar implementação.
4. Manter cada domínio com seu proprietário.
5. Reutilizar padrões comprovadamente melhores.
6. Não adicionar dependências apenas porque existem no outro projeto.
7. Toda nova integração deve ter finalidade clara.
8. Preservar isolamento por workspace/profile/publication.
9. Manter auditoria e rastreabilidade.
10. Operações externas destrutivas ou de publicação devem respeitar aprovação e idempotência.
11. Não fazer migração massiva sem necessidade.
12. Não apagar código simplesmente por parecer redundante. Confirmar uso primeiro.

---

# 13. Regra para a outra IA trabalhando no HIL

A outra IA deve:

- trabalhar somente em `C:\urdia-hil`;
- não modificar `C:\Antigomundonovo`;
- continuar evoluindo o HIL como Social/Audience Intelligence;
- usar este documento como contrato de fronteira;
- aproveitar padrões do Studio sem duplicar serviços;
- produzir contratos/interfaces quando precisar conversar com o Studio;
- manter commits/checkpoints;
- testar antes de declarar uma etapa concluída;
- parar somente quando houver necessidade real de intervenção humana.

---

# 14. Regra para o Studio

O Studio deve continuar priorizando:

1. produção de vídeo;
2. qualidade audiovisual;
3. factualidade;
4. geração de assets;
5. narração;
6. edição;
7. inspeção;
8. revisão humana;
9. SEO;
10. calendário;
11. publicação;
12. observabilidade;
13. segurança;
14. governança.

O HIL deve ser tratado como fonte complementar de sinais sociais, não como substituto do Studio.

---

# 15. Estado da assimilação

A análise realizada até o momento identificou os principais padrões do HIL que podem melhorar o Studio:

- ExecutionContext;
- Audit;
- Governance;
- Auth/session;
- Worker/jobs;
- Evidence/Verification;
- Rights/Provenance;
- Rendering infrastructure;
- Contracts;
- Provider Registry;
- Capability Registry;
- Profile architecture;
- Research separation.

Também foram identificados elementos que devem permanecer no HIL:

- Inbox;
- Audience;
- Demand;
- Social Intelligence;
- Comment workflows;
- social feedback.

**Importante:** esta análise é uma avaliação arquitetural baseada no material e na inspeção já realizada. Ela NÃO significa que todos os arquivos e todas as dependências do HIL foram auditados linha a linha nem que cada componente está pronto para ser transplantado.

Antes de qualquer assimilação física de código, o componente deve ser comparado com o equivalente existente no Studio e incorporado apenas se houver ganho arquitetural comprovado.

---

# 16. Regra final

A arquitetura desejada é:

```text
                  ┌───────────────────────┐
                  │      URDIA CORE       │
                  │                       │
                  │ Contracts             │
                  │ ExecutionContext      │
                  │ Auth                  │
                  │ Governance            │
                  │ Audit                 │
                  │ Evidence              │
                  │ Research              │
                  │ Providers             │
                  │ Capabilities          │
                  │ Jobs                  │
                  └───────────┬───────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
      ┌─────────────────┐         ┌─────────────────┐
      │ URDIA STUDIO    │         │ URDIA-HIL       │
      │                 │         │                 │
      │ 🎬 VIDEO        │         │ 💬 SOCIAL       │
      │                 │         │                 │
      │ Script          │         │ Inbox           │
      │ Research        │         │ Comments        │
      │ Storyboard      │         │ Audience        │
      │ Images          │         │ Demand          │
      │ TTS             │         │ Feedback        │
      │ Whisper         │         │ Opportunities   │
      │ Vision          │         │                 │
      │ FFmpeg          │         │                 │
      │ Review          │         │                 │
      │ SEO             │         │                 │
      │ Calendar        │         │                 │
      │ Publish         │         │                 │
      └────────┬────────┘         └────────┬────────┘
               │                           │
               └───────────┬───────────────┘
                           │
                     Contracts/Events
```

**Objetivo:** dois sistemas especializados, uma arquitetura coerente, nenhuma duplicação desnecessária.
