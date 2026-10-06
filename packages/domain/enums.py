"""Domain vocabularies — every value traced to the Constitution package.

Source documents are cited per class. Values are stored exactly as specified;
where the spec mixes Portuguese and English (knowledge/uncertainty states),
the canonical code value is the English form used by the agent contracts
(Doc 02) and the mapping is documented.
"""

from enum import StrEnum


class OpportunityState(StrEnum):
    """State machine (Doc 00 §26, Doc 03)."""

    # Main chain
    DISCOVERED = "DISCOVERED"
    NORMALIZED = "NORMALIZED"
    CLUSTERED = "CLUSTERED"
    CANDIDATE = "CANDIDATE"
    RESEARCHING = "RESEARCHING"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    FACT_CHECK = "FACT_CHECK"
    UNCERTAINTY_REVIEW = "UNCERTAINTY_REVIEW"
    OPPORTUNITY_SCORED = "OPPORTUNITY_SCORED"
    FORMAT_SELECTED = "FORMAT_SELECTED"
    PLATFORM_SELECTED = "PLATFORM_SELECTED"
    DRAFTING = "DRAFTING"
    VISUAL_PRODUCTION = "VISUAL_PRODUCTION"
    RIGHTS_CHECK = "RIGHTS_CHECK"
    SEO_CHECK = "SEO_CHECK"
    QUALITY_CONTROL = "QUALITY_CONTROL"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    ANALYZING = "ANALYZING"
    LEARNING = "LEARNING"

    # Auxiliary states
    QUARANTINED = "QUARANTINED"
    BLOCKED = "BLOCKED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    RIGHTS_BLOCKED = "RIGHTS_BLOCKED"
    FACT_CHECK_FAILED = "FACT_CHECK_FAILED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


MAIN_CHAIN_STATES: tuple[OpportunityState, ...] = (
    OpportunityState.DISCOVERED,
    OpportunityState.NORMALIZED,
    OpportunityState.CLUSTERED,
    OpportunityState.CANDIDATE,
    OpportunityState.RESEARCHING,
    OpportunityState.EVIDENCE_COLLECTED,
    OpportunityState.FACT_CHECK,
    OpportunityState.UNCERTAINTY_REVIEW,
    OpportunityState.OPPORTUNITY_SCORED,
    OpportunityState.FORMAT_SELECTED,
    OpportunityState.PLATFORM_SELECTED,
    OpportunityState.DRAFTING,
    OpportunityState.VISUAL_PRODUCTION,
    OpportunityState.RIGHTS_CHECK,
    OpportunityState.SEO_CHECK,
    OpportunityState.QUALITY_CONTROL,
    OpportunityState.HUMAN_REVIEW,
    OpportunityState.READY,
    OpportunityState.SCHEDULED,
    OpportunityState.PUBLISHED,
    OpportunityState.ANALYZING,
    OpportunityState.LEARNING,
)


class KnowledgeState(StrEnum):
    """Estados de conhecimento (Doc 00 §12). SABEMOS/ACREDITAMOS/INTERPRETAMOS/NÃO SABEMOS."""

    SABEMOS = "SABEMOS"
    ACREDITAMOS = "ACREDITAMOS"
    INTERPRETAMOS = "INTERPRETAMOS"
    NAO_SABEMOS = "NAO_SABEMOS"  # "NÃO SABEMOS" — accent dropped for storage safety


class UncertaintyState(StrEnum):
    """Estados de incerteza (Doc 00 §12); Doc 02 uses PROBABLE, Doc 16 CONTROVERSIAL."""

    CONFIRMED = "CONFIRMED"  # CONFIRMADO
    PROBABLE = "PROBABLE"  # PROVÁVEL
    POSSIBLE = "POSSIBLE"  # POSSÍVEL
    CONTROVERSIAL = "CONTROVERSIAL"  # CONTROVERSO
    UNKNOWN = "UNKNOWN"  # DESCONHECIDO
    REFUTED = "REFUTED"  # REFUTADO


class RightsClassification(StrEnum):
    """Direitos (Doc 00 §15, Doc 11). Regra absoluta: UNKNOWN = NÃO PUBLICAR."""

    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    CC0 = "CC0"
    CC_BY = "CC_BY"
    CC_BY_SA = "CC_BY_SA"
    OTHER_FREE_LICENSE = "OTHER_FREE_LICENSE"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    UNKNOWN = "UNKNOWN"
    PROHIBITED = "PROHIBITED"


BLOCKING_RIGHTS: frozenset[RightsClassification] = frozenset(
    {
        RightsClassification.UNKNOWN,
        RightsClassification.PROHIBITED,
        RightsClassification.PERMISSION_REQUIRED,
    }
)


class RightsGateOutcome(StrEnum):
    """Rights gate (Doc 11). UNKNOWN/PROHIBITED/REQUIRES_PERMISSION → BLOCK."""

    BLOCK = "BLOCK"
    MAY_PROCEED = "MAY_PROCEED"


class VisualClassification(StrEnum):
    """Classificações visuais (Doc 00 §16, Doc 10)."""

    ORIGINAL_AS_RETRIEVED = "ORIGINAL_AS_RETRIEVED"
    CROPPED = "CROPPED"
    RESTORED = "RESTORED"
    UPSCALED = "UPSCALED"
    COLORIZED = "COLORIZED"
    RECONSTRUCTED = "RECONSTRUCTED"
    AI_GENERATED = "AI_GENERATED"
    ILLUSTRATION = "ILLUSTRATION"
    UNKNOWN = "UNKNOWN"


class JobType(StrEnum):
    """Jobs (Doc 03)."""

    DISCOVERY_SCAN = "DISCOVERY_SCAN"
    SOURCE_RETRIEVAL = "SOURCE_RETRIEVAL"
    SOURCE_EXTRACTION = "SOURCE_EXTRACTION"
    SOURCE_CLUSTERING = "SOURCE_CLUSTERING"
    IMAGE_ANALYSIS = "IMAGE_ANALYSIS"
    IMAGE_RESEARCH = "IMAGE_RESEARCH"
    RIGHTS_RESEARCH = "RIGHTS_RESEARCH"
    CLAIM_EXTRACTION = "CLAIM_EXTRACTION"
    CLAIM_VERIFICATION = "CLAIM_VERIFICATION"
    ADVERSARIAL_RESEARCH = "ADVERSARIAL_RESEARCH"
    OPPORTUNITY_ANALYSIS = "OPPORTUNITY_ANALYSIS"
    FORMAT_PLANNING = "FORMAT_PLANNING"
    CONTENT_GENERATION = "CONTENT_GENERATION"
    VISUAL_GENERATION = "VISUAL_GENERATION"
    QC = "QC"
    EXPORT = "EXPORT"
    PUBLICATION = "PUBLICATION"
    ANALYTICS_SYNC = "ANALYTICS_SYNC"
    COMMENT_SYNC = "COMMENT_SYNC"
    LEARNING_ANALYSIS = "LEARNING_ANALYSIS"


class QualityGate(StrEnum):
    """Quality gates antes de READY (Doc 00 §21, Doc 03)."""

    RELEVANCE = "RELEVANCE"
    EVIDENCE = "EVIDENCE"
    FACTUALITY = "FACTUALITY"
    UNCERTAINTY = "UNCERTAINTY"
    RIGHTS = "RIGHTS"
    ORIGINALITY = "ORIGINALITY"
    VISUAL = "VISUAL"
    SEO = "SEO"
    PLATFORM = "PLATFORM"
    ANTI_SLOP = "ANTI-SLOP"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class GateResult(StrEnum):
    """QC gate results (Doc 06: PASS / WARNING / FAIL; Doc 02 human_review: REQUIRED)."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    REQUIRED = "REQUIRED"


class JEVDecision(StrEnum):
    """Decisões do JEV (Doc 12)."""

    PROCEED = "PROCEED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"
    SERIES_CANDIDATE = "SERIES_CANDIDATE"
    EXPERIMENT_CANDIDATE = "EXPERIMENT_CANDIDATE"


class AgentName(StrEnum):
    """Agentes (Doc 05). Nenhum agente possui autoridade completa (Doc 00 §8)."""

    SCOUT = "SCOUT"
    RESEARCHER = "RESEARCHER"
    CLAIM_ANALYST = "CLAIM_ANALYST"
    ADVERSARIAL_RESEARCHER = "ADVERSARIAL_RESEARCHER"
    SOURCE_ANALYST = "SOURCE_ANALYST"
    ARCHIVIST = "ARCHIVIST"
    RIGHTS_ANALYST = "RIGHTS_ANALYST"
    EDITORIAL_ANALYST = "EDITORIAL_ANALYST"
    JEV = "JEV"
    FORMAT_PLANNER = "FORMAT_PLANNER"
    PLATFORM_PLANNER = "PLATFORM_PLANNER"
    COPYWRITER = "COPYWRITER"
    VISUAL_DIRECTOR = "VISUAL_DIRECTOR"
    QC_ANALYST = "QC_ANALYST"
    AUDIENCE_ANALYST = "AUDIENCE_ANALYST"
    LEARNING_AGENT = "LEARNING_AGENT"


class ContentFormat(StrEnum):
    """Formatos V1 (Doc 13)."""

    PHOTO_POST = "PHOTO_POST"
    CAROUSEL = "CAROUSEL"
    MICROLOOP = "MICROLOOP"


class PublicationMethod(StrEnum):
    """Métodos de plataforma (Doc 14)."""

    API = "API"
    MANUAL = "MANUAL"
    EXPORT = "EXPORT"
    UNAVAILABLE = "UNAVAILABLE"


class PlatformErrorKind(StrEnum):
    """Error normalization (Doc 14)."""

    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    SERVER_ERROR = "SERVER_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNAVAILABLE = "UNAVAILABLE"


class HealthState(StrEnum):
    """Health states (Doc 07)."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    QUOTA_LIMITED = "QUOTA_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class QuarantineState(StrEnum):
    """Quarantine flow (Doc 09)."""

    QUARANTINED = "QUARANTINED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    REASSESSMENT_DUE = "REASSESSMENT_DUE"
    CLEARED = "CLEARED"
    REJECTED = "REJECTED"


class MetricName(StrEnum):
    """Normalized metrics (Doc 15)."""

    REACH = "REACH"
    IMPRESSIONS = "IMPRESSIONS"
    VIEWS = "VIEWS"
    SAVES = "SAVES"
    SHARES = "SHARES"
    COMMENTS = "COMMENTS"
    CLICKS = "CLICKS"
    FOLLOWERS_GAINED = "FOLLOWERS_GAINED"
    RETENTION = "RETENTION"
    REPLAYS = "REPLAYS"
    RESPONSES = "RESPONSES"
    PARTICIPATION = "PARTICIPATION"
    CONVERSION = "CONVERSION"


class QualifiedSignal(StrEnum):
    """Qualified learning signals (Doc 15)."""

    SOURCE_REQUEST = "SOURCE_REQUEST"
    CORRECTION = "CORRECTION"
    DOCUMENT_SUBMISSION = "DOCUMENT_SUBMISSION"
    TESTIMONY = "TESTIMONY"
    RECURRING_QUESTION = "RECURRING_QUESTION"
    CONTINUATION_REQUEST = "CONTINUATION_REQUEST"
    AUDIENCE_DISCOVERY = "AUDIENCE_DISCOVERY"


def rights_gate(classification: RightsClassification) -> RightsGateOutcome:
    """Deterministic rights gate (Doc 11). Fail closed: anything not explicitly
    VERIFIED-equivalent blocks. UNKNOWN = NÃO PUBLICAR (Doc 00 §15)."""
    if classification in BLOCKING_RIGHTS:
        return RightsGateOutcome.BLOCK
    return RightsGateOutcome.MAY_PROCEED


class MemoryKind(StrEnum):
    """Auxiliary memory types (Doc 05 §Memory, V2.2 Hermes)."""

    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    RULE = "RULE"
    EXPERIENCE = "EXPERIENCE"
    HYPOTHESIS = "HYPOTHESIS"
    SKILL = "SKILL"


class MemoryStatus(StrEnum):
    """Lifecycle of an auxiliary memory entry. Superseding archives the old
    entry (append-only corrections, Doc 08)."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
