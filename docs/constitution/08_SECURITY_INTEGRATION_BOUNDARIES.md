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

## URDIA account authentication
V1 uses normalized email + password and creates a private workspace for each
new account. Passwords use Argon2id; the API issues an opaque, random,
HttpOnly/SameSite cookie and persists only its SHA-256 digest with a 12-hour
expiry. Protected API routers require both a valid session and workspace
membership; workspace IDs supplied by the browser are not authorization.
Login failures are rate-limited per client IP. Session and auth responses are
not cacheable. Unsafe browser requests require an exact allowed `Origin` to
prevent cross-site request forgery; login responses do not distinguish unknown
accounts from incorrect passwords.

Email must be verified before login. Verification and password recovery use
single-use random tokens; only token digests are persisted. Delivery uses
configured SMTP with STARTTLS by default; message links and tokens are never
logged. Password reset revokes every active URDIA session. Account-action
request endpoints have the same response regardless of whether an account
exists.

This local-first milestone does not yet implement MFA, distributed rate-limit
storage, or external account connections. Do not expose self-registration
publicly until production-grade shared rate limiting and MFA are available.
External OAuth tokens remain backend-only and are not implemented by this
milestone.

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
