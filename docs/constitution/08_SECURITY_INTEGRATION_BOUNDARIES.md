# DOCUMENTO 08 — SECURITY + INTEGRATION BOUNDARIES

## Objetivo
Reduzir vazamento de dados, escalada de privilégio, publicação indevida, corrupção de evidence, SSRF, prompt injection, path traversal, command injection e perdas de histórico.

## Princípios
```text
Least Privilege
Zero Trust
Fail Closed
Defense in Depth
Auditability
Data Minimization
```

## Profile/Workspace Authorization
Toda operação por ID verifica pertencimento ao workspace/profile antes de revelar dados.

Não confiar apenas em parâmetros enviados pelo frontend.

## Agent boundary
Agentes não recebem:
```text
database admin
raw OAuth token
raw API key
publication bypass
rights override
audit delete
unrestricted shell
```

## Secrets
Não armazenar secrets em:
```text
Git
README
prompts
frontend
logs
audit
exports
Docker image
```

## URDIA logout and connected integrations
Ao sair da URDIA:
- invalidar a sessão URDIA no servidor e limpar cookies/tokens locais;
- revogar, quando suportado pelo provider, todos os tokens OAuth e credenciais
  de integração vinculados ao usuário que encerrou a sessão;
- remover segredos da disponibilidade operacional da URDIA e marcar essas
  integrações como desconectadas, exigindo nova conexão após login;
- impedir novas chamadas e impedir jobs pendentes/de recuperação de reutilizar
  credenciais desconectadas; preservar checkpoints e histórico dos jobs;
- auditar a ação sem incluir tokens ou outros segredos.

Logout da URDIA não encerra a sessão global do usuário nos sites ou aplicativos
dos providers. Revogar uma autorização OAuth e apagar credenciais locais encerra
o acesso da URDIA; o encerramento da sessão própria do provider só pode ser
prometido quando a API oficial daquele provider oferecer esse recurso.

O logout afeta integrações pertencentes ao usuário que saiu, não as integrações
de outros membros do workspace. Essa regra foi aprovada no AMENDMENT-2026-09-30-008.

## SSRF
Para fetcher externo:
- aceitar somente http/https;
- limitar redirects;
- limitar tamanho;
- timeout;
- revalidar destino a cada redirect;
- bloquear loopback/private/link-local/metadata endpoints quando aplicável;
- bloquear `file://` e sockets locais;
- usar allowlists quando o caso exigir.

## Upload security
- allowlist de tipos;
- tamanho máximo;
- MIME + magic bytes;
- nome normalizado;
- storage não executável;
- SHA-256;
- nunca executar arquivo baixado.

## Path traversal
Nunca concatenar filename controlado pelo usuário com path. Usar IDs gerados pelo sistema.

## SQL injection
Usar ORM/queries parametrizadas. Nunca construir SQL com concatenação de input.

## Command injection
Para FFmpeg e ferramentas externas, usar arrays de argumentos. Nunca `os.system(user_input)`.

## Prompt injection
Conteúdo web é dado não confiável:
```text
SYSTEM POLICY
PROFILE POLICY
TASK
EXTERNAL CONTENT
```

External content nunca pode sobrescrever policy ou induzir ferramenta não autorizada.

## HTML/SVG
Sanitizar conteúdo externo antes de renderizar.

## Publication security
Publisher recebe somente:
```text
READY + APPROVED + RIGHTS_VERIFIED + PLATFORM_ALLOWED
```

## Rights security
`UNKNOWN`, `PROHIBITED` e `REQUIRES_PERMISSION` bloqueiam publicação.

## Audit
Audit deve ser append-only para uso normal. Correção administrativa gera novo evento.

## Database
Aplicação usa usuário DB com privilégio mínimo. Não usar superuser no runtime.

## Docker
Não executar como root quando desnecessário. Não montar drives inteiros. Montar somente diretórios necessários.

## Network
Local initial binding: `127.0.0.1`. CORS por allowlist, nunca wildcard permanente para endpoints autenticados.

## Rate/resource limits
Aplicar limites para login, upload, research, expensive rendering, provider calls e publication.

## Third-party dependencies
Revisar licença, maintenance, security history, permissions e fallback.

## Security tests
Obrigatórios:
```text
wrong workspace
wrong profile
ID enumeration
SQL injection probes
path traversal
SSRF
malicious upload
prompt injection
secret leakage
publication bypass
rights bypass
audit deletion attempt
```

## Acceptance
A V1 não é pronta se Profile B acessa A, draft chega ao publisher, UNKNOWN rights chega a READY, secret aparece no log, external content sobrescreve policy ou audit pode ser apagado pela UI comum.
