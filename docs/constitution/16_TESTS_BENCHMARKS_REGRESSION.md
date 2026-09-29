# DOCUMENTO 16 — TESTS + BENCHMARKS + REGRESSION

## Test levels
```text
unit
integration
contract
governance
security
profile_isolation
provider
frontend
e2e
regression
benchmark
```

## Must-pass rules
### Fact
Claim without evidence → `NOT_READY`.

### Rights
```text
UNKNOWN → RIGHTS_BLOCKED
PROHIBITED → RIGHTS_BLOCKED
REQUIRES_PERMISSION → RIGHTS_BLOCKED
```

### Conflict
Independent contradictory sources → `CONTROVERSIAL` and preserve both sides.

### Originality
Test exact copy, near-copy e semantic copy. Copied content requires transformation/research.

### Duplicate image
Hash + perceptual hash + semantic match.

### Provider
Primary unavailable → fallback with same contract and audit.

### Platform
Platform down → content remains valid and manual fallback remains available.

### Recovery
Worker killed → checkpoint resume.

### Isolation
Profile B cannot access A private content, sources, metrics, rules or calendar.

### Generalized learning
B may receive generalized rule, never private context from A.

### Prompt injection
External text attempting instruction takeover must be treated as data.

### SSRF
Probe loopback/private/metadata URLs. Must block according to fetcher policy.

### Path traversal
Malicious filenames cannot escape allowed storage root.

### Secret leakage
No keys/tokens/passwords in logs, API payloads, frontend, audit or exports.

### Publication bypass
Draft/blocked content cannot reach publisher endpoint.

## Benchmark
Initial ANM set: 100–300 cases, covering true/false/ambiguous/conflicting claims, identified/unknown photos, current news, documents, What If, licensed/unlicensed assets.

## Model regression
```text
benchmark → regression → compare → approve → promote
```

## Prompt regression
Check schema, factuality, uncertainty, rights behavior, anti-slop and originality.

## Rendering regression
Check dimensions, overflow, fonts, contrast, asset placement and audio length.

## CI
```text
lint
format/type check
unit
integration
contract
governance
security
isolation
regression
```

## Release gate
Do not release when critical isolation, rights, evidence, contracts or security tests fail.
