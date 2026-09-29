"""Agent output contracts (Doc 02 — "Agent contracts").

Each model mirrors the exact JSON specified. Agent outputs are validated with
parse → schema → semantic → policy before persisting (Doc 05); a failure never
produces an invented output (Doc 05 "Failure").
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from packages.domain.enums import (
    ContentFormat,
    GateResult,
    JEVDecision,
    QualityGate,
    RightsClassification,
    UncertaintyState,
    VisualClassification,
)


def _upper(v: Any) -> Any:
    """Doc 02's JEV example writes decisions lowercase ("needs_research") while
    Doc 12 lists them uppercase (NEEDS_RESEARCH); normalize the wire format."""
    return v.upper() if isinstance(v, str) else v


class ScoutCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    subject_type: str = ""
    discovery_reason: str = ""
    why_now: str = ""
    possible_angles: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class ScoutOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: ScoutCandidate
    needs_research: bool = True


class ClaimAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: UncertaintyState
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    uncertainty: str = ""


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_ids: list[str] = Field(default_factory=list)
    description: str
    source_ids: list[str] = Field(default_factory=list)


class ResearcherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimAssessment] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_research_actions: list[str] = Field(default_factory=list)


class RightsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    classification: RightsClassification
    license: str | None = None
    license_url: str | None = None
    attribution: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    status: RightsClassification | None = None
    evidence_source_ids: list[str] = Field(default_factory=list)


class JEVRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Annotated[JEVDecision, BeforeValidator(_upper)]
    priority: str = "MEDIUM"
    why_now: str = ""
    why_profile: str = ""
    recommended_format: ContentFormat | str | None = None
    recommended_platforms: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class JEVOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: JEVRecommendation
    requires_human_review: bool = True


class CopywriterSEO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)


class CarouselSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    text: str
    asset_id: str | None = None
    role: str | None = None  # HOOK/ORIENTATION/EVIDENCE/CONTEXT/DISCOVERY/MEANING/SOURCE (Doc 13)


class CopywriterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    caption: str
    slides: list[CarouselSlide] = Field(default_factory=list)
    microloop_text: str | None = None
    cta: dict[str, Any] | None = None
    seo: CopywriterSEO = Field(default_factory=CopywriterSEO)
    claim_ids_used: list[str] = Field(default_factory=list)


class AssetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    usage: str
    crop: dict[str, Any] | None = None
    transformation: VisualClassification | None = None


class VisualDirectorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: str
    asset_usage: list[AssetUsage] = Field(default_factory=list)
    new_asset_required: bool = False
    ai_generation_allowed: bool = False
    reason: str = ""


class QCGates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: GateResult = GateResult.PASS
    evidence: GateResult = GateResult.PASS
    factuality: GateResult = GateResult.PASS
    uncertainty: GateResult = GateResult.PASS
    rights: GateResult = GateResult.PASS
    originality: GateResult = GateResult.PASS
    visual: GateResult = GateResult.PASS
    seo: GateResult = GateResult.PASS
    platform: GateResult = GateResult.PASS
    anti_slop: GateResult = GateResult.PASS
    human_review: GateResult = GateResult.REQUIRED


class QCOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GateResult
    gates: QCGates = Field(default_factory=QCGates)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)


def quality_gate_names() -> list[str]:
    """All gate keys required by Doc 02's QC contract / Doc 03 gate list."""
    return [g.value.lower().replace("-", "_") for g in QualityGate]
