"""Every enum value here is asserted against the Constitution's exact lists
(Doc 00 §12/15/16/21/26, Doc 03, Doc 05, Doc 07, Doc 09, Doc 12, Doc 13, Doc 14)."""

from packages.domain.enums import (
    MAIN_CHAIN_STATES,
    AgentName,
    ContentFormat,
    HealthState,
    JEVDecision,
    JobType,
    KnowledgeState,
    OpportunityState,
    PlatformErrorKind,
    PublicationMethod,
    QualityGate,
    QuarantineState,
    RightsClassification,
    RightsGateOutcome,
    UncertaintyState,
    VisualClassification,
    rights_gate,
)


def test_opportunity_main_chain_is_the_specified_linear_order():
    expected = [
        "DISCOVERED", "NORMALIZED", "CLUSTERED", "CANDIDATE", "RESEARCHING",
        "EVIDENCE_COLLECTED", "FACT_CHECK", "UNCERTAINTY_REVIEW",
        "OPPORTUNITY_SCORED", "FORMAT_SELECTED", "PLATFORM_SELECTED", "DRAFTING",
        "VISUAL_PRODUCTION", "RIGHTS_CHECK", "SEO_CHECK", "QUALITY_CONTROL",
        "HUMAN_REVIEW", "READY", "SCHEDULED", "PUBLISHED", "ANALYZING", "LEARNING",
    ]
    assert [s.value for s in MAIN_CHAIN_STATES] == expected
    assert len(OpportunityState) == 30  # 22 main + 8 auxiliary


def test_opportunity_auxiliary_states():
    aux = {"QUARANTINED", "BLOCKED", "NEEDS_RESEARCH", "RIGHTS_BLOCKED",
           "FACT_CHECK_FAILED", "DUPLICATE", "REJECTED", "CANCELLED"}
    all_states = {s.value for s in OpportunityState}
    assert aux <= all_states


def test_uncertainty_states_doc00():
    assert {s.value for s in UncertaintyState} == {
        "CONFIRMED", "PROBABLE", "POSSIBLE", "CONTROVERSIAL", "UNKNOWN", "REFUTED"
    }


def test_rights_classes_doc00_and_unknown_blocks():
    assert {r.value for r in RightsClassification} == {
        "PUBLIC_DOMAIN", "CC0", "CC_BY", "CC_BY_SA", "OTHER_FREE_LICENSE",
        "PERMISSION_REQUIRED", "UNKNOWN", "PROHIBITED",
    }


def test_rights_gate_fails_closed():
    assert rights_gate(RightsClassification.UNKNOWN) is RightsGateOutcome.BLOCK
    assert rights_gate(RightsClassification.PROHIBITED) is RightsGateOutcome.BLOCK
    assert rights_gate(RightsClassification.PERMISSION_REQUIRED) is RightsGateOutcome.BLOCK
    assert rights_gate(RightsClassification.PUBLIC_DOMAIN) is RightsGateOutcome.MAY_PROCEED
    assert rights_gate(RightsClassification.CC0) is RightsGateOutcome.MAY_PROCEED
    assert rights_gate(RightsClassification.CC_BY) is RightsGateOutcome.MAY_PROCEED


def test_visual_classifications_doc00():
    assert {v.value for v in VisualClassification} == {
        "ORIGINAL_AS_RETRIEVED", "CROPPED", "RESTORED", "UPSCALED", "COLORIZED",
        "RECONSTRUCTED", "AI_GENERATED", "ILLUSTRATION", "UNKNOWN",
    }


def test_job_types_doc03_complete():
    assert {j.value for j in JobType} == {
        "DISCOVERY_SCAN", "SOURCE_RETRIEVAL", "SOURCE_EXTRACTION", "SOURCE_CLUSTERING",
        "IMAGE_ANALYSIS", "IMAGE_RESEARCH", "RIGHTS_RESEARCH", "CLAIM_EXTRACTION",
        "CLAIM_VERIFICATION", "ADVERSARIAL_RESEARCH", "OPPORTUNITY_ANALYSIS",
        "FORMAT_PLANNING", "CONTENT_GENERATION", "VISUAL_GENERATION", "QC", "EXPORT",
        "PUBLICATION", "ANALYTICS_SYNC", "COMMENT_SYNC", "LEARNING_ANALYSIS",
    }


def test_quality_gates_doc00_doc03():
    assert {g.value for g in QualityGate} == {
        "RELEVANCE", "EVIDENCE", "FACTUALITY", "UNCERTAINTY", "RIGHTS",
        "ORIGINALITY", "VISUAL", "SEO", "PLATFORM", "ANTI-SLOP", "HUMAN_REVIEW",
    }


def test_jev_decisions_doc12():
    assert {d.value for d in JEVDecision} == {
        "PROCEED", "NEEDS_RESEARCH", "QUARANTINE", "REJECT",
        "SERIES_CANDIDATE", "EXPERIMENT_CANDIDATE",
    }


def test_agents_doc05_sixteen():
    assert len(AgentName) == 16
    assert {a.value for a in AgentName} == {
        "SCOUT", "RESEARCHER", "CLAIM_ANALYST", "ADVERSARIAL_RESEARCHER",
        "SOURCE_ANALYST", "ARCHIVIST", "RIGHTS_ANALYST", "EDITORIAL_ANALYST",
        "JEV", "FORMAT_PLANNER", "PLATFORM_PLANNER", "COPYWRITER",
        "VISUAL_DIRECTOR", "QC_ANALYST", "AUDIENCE_ANALYST", "LEARNING_AGENT",
    }


def test_formats_doc13_v1():
    assert {f.value for f in ContentFormat} == {"PHOTO_POST", "CAROUSEL", "MICROLOOP"}


def test_platform_methods_doc14():
    assert {m.value for m in PublicationMethod} == {"API", "MANUAL", "EXPORT", "UNAVAILABLE"}
    assert {e.value for e in PlatformErrorKind} == {
        "AUTH_ERROR", "RATE_LIMIT", "POLICY_BLOCKED", "INVALID_PAYLOAD",
        "SERVER_ERROR", "NETWORK_ERROR", "UNAVAILABLE",
    }


def test_health_and_quarantine_states():
    assert {h.value for h in HealthState} == {
        "HEALTHY", "DEGRADED", "UNAVAILABLE", "QUOTA_LIMITED", "AUTH_ERROR", "POLICY_BLOCKED"
    }
    assert {q.value for q in QuarantineState} == {
        "QUARANTINED", "AWAITING_CONFIRMATION", "REASSESSMENT_DUE", "CLEARED", "REJECTED"
    }


def test_knowledge_states_doc00():
    assert {k.value for k in KnowledgeState} == {
        "SABEMOS", "ACREDITAMOS", "INTERPRETAMOS", "NAO_SABEMOS"
    }
