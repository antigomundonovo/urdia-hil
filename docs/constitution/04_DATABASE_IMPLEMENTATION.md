# DOCUMENTO 04 — DATABASE IMPLEMENTATION SPEC

## Engine
```text
PostgreSQL + pgvector
```

## Conventions
- UUID para IDs;
- TIMESTAMPTZ para eventos;
- SQL snake_case;
- Alembic para migrations.

## Core tables
```text
users
workspaces
workspace_members
profiles
providers
capabilities
jobs
job_steps
audit_events
```

## Research tables
```text
sources
retrievals
source_relations
discovery_items
discovery_clusters
```

## Knowledge tables
```text
entities
events
stories
story_entities
story_events
claims
evidence_records
contradictions
verdicts
```

## Asset tables
```text
assets
asset_versions
rights_records
```

## Editorial tables
```text
opportunities
opportunity_sources
opportunity_claims
opportunity_assets
format_plans
platform_plans
canonical_contents
content_packages
platform_variants
drafts
```

## Publishing tables
```text
publications
calendar_items
metric_events
comments
```

## Learning tables
```text
experiments
experiment_variants
learning_records
rules
```

## Competitor tables
```text
competitors
competitor_contents
```

## Profile fields
```text
id
workspace_id
key
name
language
audience_region
editorial_policy JSONB
visual_identity JSONB
content_taxonomy JSONB
platform_policy JSONB
source_preferences JSONB
risk_policy JSONB
cta_policy JSONB
seo_policy JSONB
automation_level
status
created_at
updated_at
```

Unique: `(workspace_id, key)`.

## Source fields
```text
id workspace_id profile_id publisher author title url canonical_url source_type publication_date event_proximity language jurisdiction access_type archive_status reliability_profile correction_history metadata first_seen_at last_seen_at created_at updated_at
```

## Claim fields
```text
id workspace_id profile_id story_id subject predicate object normalized_text claim_type temporal_scope geographic_scope importance status confidence interpretation_flag editorial_wording last_reviewed_at created_at updated_at
```

## Evidence fields
```text
id workspace_id profile_id claim_id source_id evidence_type excerpt page_reference url snapshot_reference supports strength independence_group retrieved_at metadata created_at
```

## Asset fields
```text
id workspace_id profile_id asset_type original_file_url page_url institution creator creation_date license license_url attribution_text retrieval_date file_hash perceptual_hash embedding rights_confidence visual_classification status created_at updated_at
```

## Rights fields
```text
id workspace_id profile_id asset_id classification license license_url rights_holder attribution_required attribution_text territory commercial_use modification_allowed evidence_source_id confidence status verified_at verified_by notes created_at updated_at
```

## Opportunity fields
```text
id workspace_id profile_id story_id title description why_now why_profile editorial_analysis risk_analysis timing_analysis novelty_analysis decision decision_reason priority status created_at updated_at
```

## Job fields
```text
id workspace_id profile_id job_type status priority payload result attempt max_attempts checkpoint error created_at started_at finished_at
```

## Audit
```text
id workspace_id profile_id actor_id entity_type entity_id action previous_state new_state reason evidence_ids rule_version model provider timestamp metadata
```

## JSONB rule
Use JSONB para metadata/configuration/experimental data. Não esconder relações centrais dentro de JSONB.

## Delete policy
Evitar cascade delete em evidence, claims, audit, publications, metrics, decisions e learning. Preferir archive/retire.

## Indexes
Indexar `workspace_id`, `profile_id`, status, created_at, scheduled_for, canonical_url, file_hash, perceptual_hash, claim_id, source_id, publication_id e audit timestamp.

## Seeds
Somente ambiente de desenvolvimento; nunca secrets.

## Critical DB tests
- FK integrity;
- profile/workspace isolation;
- READY restrictions;
- audit creation;
- job checkpoints;
- backup/restore.
