"""Agent contracts must accept exactly the JSON shapes specified in Doc 02."""

import pytest
from pydantic import ValidationError

from packages.contracts.agent_io import GenericAgentInput, GenericAgentOutput
from packages.contracts.agents import (
    CopywriterOutput,
    JEVOutput,
    QCOutput,
    ResearcherOutput,
    RightsOutput,
    ScoutOutput,
    VisualDirectorOutput,
    quality_gate_names,
)
from packages.domain.enums import UncertaintyState


def test_generic_input_doc02_example():
    payload = {
        "schema_version": "1.0",
        "execution": {
            "job_id": "", "workspace_id": "", "profile_id": "", "actor_id": "", "correlation_id": ""
        },
        "task": {"type": "", "instructions": ""},
        "context": {},
        "allowed_capabilities": [],
        "constraints": {},
    }
    model = GenericAgentInput.model_validate(payload)
    assert model.schema_version == "1.0"
    with pytest.raises(ValidationError):
        GenericAgentInput.model_validate({**payload, "schema_version": "2.0"})


def test_generic_output_doc02_example():
    payload = {
        "schema_version": "1.0",
        "status": "OK",
        "result": {},
        "evidence_ids": [],
        "source_ids": [],
        "uncertainties": [],
        "warnings": [],
        "recommended_next_action": None,
    }
    assert GenericAgentOutput.model_validate(payload)


def test_scout_output_doc02_example():
    payload = {
        "candidate": {
            "title": "", "summary": "", "subject_type": "", "discovery_reason": "",
            "why_now": "", "possible_angles": [], "source_ids": [], "asset_ids": [],
        },
        "needs_research": True,
    }
    assert ScoutOutput.model_validate(payload)


def test_researcher_output_doc02_example():
    payload = {
        "claims": [
            {"claim_id": "", "status": "PROBABLE", "evidence_ids": [], "source_ids": [],
             "reason": "", "uncertainty": ""}
        ],
        "contradictions": [],
        "missing_evidence": [],
        "next_research_actions": [],
    }
    model = ResearcherOutput.model_validate(payload)
    assert model.claims[0].status is UncertaintyState.PROBABLE


def test_rights_output_doc02_example():
    payload = {
        "asset_id": "", "classification": "UNKNOWN", "license": "", "license_url": "",
        "attribution": "", "confidence": 0, "status": "UNKNOWN", "evidence_source_ids": [],
    }
    model = RightsOutput.model_validate(payload)
    assert model.classification.value == "UNKNOWN"


def test_rights_confidence_bounded():
    with pytest.raises(ValidationError):
        RightsOutput.model_validate(
            {"asset_id": "a", "classification": "CC_BY", "confidence": 1.5}
        )


def test_jev_output_doc02_example():
    payload = {
        "recommendation": {
            "decision": "needs_research", "priority": "MEDIUM", "why_now": "",
            "why_profile": "", "recommended_format": "", "recommended_platforms": [],
            "risks": [], "alternatives": [],
        },
        "requires_human_review": True,
    }
    model = JEVOutput.model_validate(payload)
    assert model.recommendation.decision.value == "NEEDS_RESEARCH"
    assert model.requires_human_review is True


def test_copywriter_output_doc02_example():
    payload = {
        "title": "", "caption": "", "slides": [], "microloop_text": "", "cta": None,
        "seo": {"entities": [], "keywords": [], "search_queries": []},
        "claim_ids_used": [],
    }
    assert CopywriterOutput.model_validate(payload)


def test_visual_director_output_doc02_example():
    payload = {
        "strategy": "", "asset_usage": [], "new_asset_required": False,
        "ai_generation_allowed": False, "reason": "",
    }
    assert VisualDirectorOutput.model_validate(payload)


def test_qc_output_doc02_example_gates_complete():
    payload = {
        "status": "PASS",
        "gates": {
            "relevance": "PASS", "evidence": "PASS", "factuality": "PASS",
            "uncertainty": "PASS", "rights": "PASS", "originality": "PASS",
            "visual": "PASS", "seo": "PASS", "platform": "PASS", "anti_slop": "PASS",
            "human_review": "REQUIRED",
        },
        "blocking_issues": [], "warnings": [], "required_revisions": [],
    }
    model = QCOutput.model_validate(payload)
    assert model.gates.human_review.value == "REQUIRED"
    assert set(quality_gate_names()) == set(payload["gates"].keys())


def test_qc_rejects_unknown_gate_keys():
    payload = {"status": "PASS", "gates": {"relevance": "PASS", "made_up_gate": "PASS"}}
    with pytest.raises(ValidationError):
        QCOutput.model_validate(payload)
