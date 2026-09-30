# DOCUMENTO 02 — DATABASE MODEL + JSON CONTRACTS + INTERNAL APIs

## Core entities
```text
User Workspace WorkspaceMember Profile
Source Retrieval SourceRelation
Entity Event Story Claim EvidenceRecord Contradiction Verdict
Asset AssetVersion RightsRecord
Opportunity FormatPlan PlatformPlan
CanonicalContent ContentPackage PlatformVariant Draft
Publication MetricEvent Comment
Experiment ExperimentVariant LearningRecord Rule
Job JobStep Provider Capability AuditEvent CalendarItem
Competitor CompetitorContent DiscoveryItem DiscoveryCluster
```

## API
```text
/api/v1/
```

### Profiles
```http
GET    /api/v1/profiles
POST   /api/v1/profiles
GET    /api/v1/profiles/{profile_id}
PATCH  /api/v1/profiles/{profile_id}
```

### Sources
```http
GET  /api/v1/profiles/{profile_id}/sources
POST /api/v1/profiles/{profile_id}/sources
GET  /api/v1/sources/{source_id}
POST /api/v1/sources/{source_id}/retrieve
```

### Opportunities
```http
GET  /api/v1/profiles/{profile_id}/opportunities
POST /api/v1/profiles/{profile_id}/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/opportunities/{id}/research
POST /api/v1/opportunities/{id}/decide
POST /api/v1/opportunities/{id}/quarantine
POST /api/v1/opportunities/{id}/reject
```

`GET /api/v1/opportunities/{id}` returns attached claim IDs, editorial wording
and verification status for the opportunity's workspace so the editor can
record which claims the draft actually uses.

### Content
```http
POST /api/v1/opportunities/{id}/create-content
POST /api/v1/content/{id}/generate-draft
POST /api/v1/content/{id}/generate-visual
POST /api/v1/content/{id}/run-qc
POST /api/v1/content/{id}/approve
POST /api/v1/content/{id}/reject
POST /api/v1/content/{id}/export
GET  /api/v1/content/{id}/export/download
```

O download entrega um ZIP temporário com a pasta de exportação; credenciais
de workspace/profile continuam obrigatórias e o backend revalida os gates.

### Publication
```http
GET  /api/v1/publications
POST /api/v1/publications/{id}/retry
POST /api/v1/publications/{id}/manual-fallback
```

### Analytics / Learning / Jobs / Governance
```http
GET /api/v1/analytics/overview
GET /api/v1/analytics/publications/{publication_id}
GET /api/v1/analytics/comments
GET /api/v1/analytics/qualified-signals
GET /api/v1/learning
POST /api/v1/learning/experiments
POST /api/v1/learning/rules/{id}/review
POST /api/v1/learning/rules/{id}/activate
GET /api/v1/jobs
GET /api/v1/jobs/{id}
POST /api/v1/jobs/{id}/retry
POST /api/v1/jobs/{id}/cancel
GET /api/v1/providers
GET /api/v1/capabilities
GET /api/v1/health
GET /api/v1/audit
```

## Generic Agent Input
```json
{
  "schema_version":"1.0",
  "execution":{"job_id":"","workspace_id":"","profile_id":"","actor_id":"","correlation_id":""},
  "task":{"type":"","instructions":""},
  "context":{},
  "allowed_capabilities":[],
  "constraints":{}
}
```

## Generic Agent Output
```json
{
  "schema_version":"1.0",
  "status":"OK",
  "result":{},
  "evidence_ids":[],
  "source_ids":[],
  "uncertainties":[],
  "warnings":[],
  "recommended_next_action":null
}
```

## Agent contracts
### Scout
```json
{"candidate":{"title":"","summary":"","subject_type":"","discovery_reason":"","why_now":"","possible_angles":[],"source_ids":[],"asset_ids":[]},"needs_research":true}
```
### Researcher
```json
{"claims":[{"claim_id":"","status":"PROBABLE","evidence_ids":[],"source_ids":[],"reason":"","uncertainty":""}],"contradictions":[],"missing_evidence":[],"next_research_actions":[]}
```
### Rights
```json
{"asset_id":"","classification":"","license":"","license_url":"","attribution":"","confidence":0,"status":"UNKNOWN","evidence_source_ids":[]}
```
### JEV
```json
{"recommendation":{"decision":"needs_research","priority":"MEDIUM","why_now":"","why_profile":"","recommended_format":"","recommended_platforms":[],"risks":[],"alternatives":[]},"requires_human_review":true}
```
### Copywriter
```json
{"title":"","caption":"","slides":[],"microloop_text":"","cta":null,"seo":{"entities":[],"keywords":[],"search_queries":[]},"claim_ids_used":[]}
```
### Visual Director
```json
{"strategy":"","asset_usage":[{"asset_id":"","usage":"","crop":null,"transformation":null}],"new_asset_required":false,"ai_generation_allowed":false,"reason":""}
```
### QC
```json
{"status":"PASS","gates":{"relevance":"PASS","evidence":"PASS","factuality":"PASS","uncertainty":"PASS","rights":"PASS","originality":"PASS","visual":"PASS","seo":"PASS","platform":"PASS","anti_slop":"PASS","human_review":"REQUIRED"},"blocking_issues":[],"warnings":[],"required_revisions":[]}
```

## Validation
```text
parse → schema validation → semantic validation → policy validation → persist
```

Nunca permitir publisher endpoint fora de `READY + APPROVED + RIGHTS VERIFIED + PLATFORM ALLOWED`.
