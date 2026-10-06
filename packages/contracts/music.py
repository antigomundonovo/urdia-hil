"""Music Intelligence contracts (referência MusicIntelligence; Emenda 014).

MusicDNA = dimensão inteligente da música (não é "um MP3 anexado").
TrendSignal = sinal de tendência com proveniência — TREND SIGNAL ≠ LICENSE:
popularidade/viral NUNCA vira direito de uso.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Estados de direitos (referência §7). UNKNOWN e BLOCKED NUNCA são seguros.
RightsState = Literal["ORIGINAL", "LICENSED", "PLATFORM_LIMITED", "UNKNOWN", "BLOCKED"]

# Estados de tendência (referência §13) — sempre acompanhados de reasons.
TrendState = Literal[
    "HUGE_SATURATED",
    "SMALL_ACCELERATING",
    "PLATFORM_LOCAL",
    "CROSS_PLATFORM",
    "EMERGING",
    "DECAYING",
    "RECURRING",
    "SEASONAL",
    "RIGHTS_BLOCKED",
]


class MusicStructure(BaseModel):
    """Estrutura da faixa em segundos (referência §9)."""

    intro_seconds: int | None = Field(default=None, ge=0)
    build_seconds: int | None = Field(default=None, ge=0)
    climax_seconds: int | None = Field(default=None, ge=0)
    release_seconds: int | None = Field(default=None, ge=0)
    silence_windows: list[tuple[int, int]] = Field(default_factory=list)


class MusicDNA(BaseModel):
    """DNA musical normalizado (referência §9).

    Idioma da MÚSICA é independente do idioma do conteúdo (§21):
    vídeo pt-BR + música instrumental de qualquer origem é válido.
    Campos desconhecidos ficam None — nunca inventados.
    """

    genre: str | None = None
    subgenre: str | None = None
    bpm: float | None = Field(default=None, ge=0)
    energy: float | None = Field(default=None, ge=0, le=1)
    tension: float | None = Field(default=None, ge=0, le=1)
    rhythmic_density: float | None = Field(default=None, ge=0, le=1)
    instrumentation: list[str] = Field(default_factory=list)
    texture: str | None = None
    vocal_mode: Literal["instrumental", "vocal", "UNKNOWN"] | None = None
    music_language_code: str | None = None  # canônico ("pt"), nunca "pt-br"
    music_locale_code: str | None = None
    structure: MusicStructure | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    narrative_role: str | None = None  # ex. "background", "driver"
    visual_context: str | None = None
    region: str | None = None

    def fingerprint(self) -> tuple:
        """Assinatura normalizada para correlação cross-platform (§11):
        características normalizadas, NUNCA nome de música."""
        bpm_bucket = int(self.bpm // 10) if self.bpm else None
        energy_bucket = int((self.energy or 0) * 5) if self.energy is not None else None
        return (
            (self.genre or "").lower(),
            bpm_bucket,
            energy_bucket,
            self.vocal_mode or "UNKNOWN",
        )


class TrendComponents(BaseModel):
    """Componentes SEPARADOS de tendência (referência §12) — proibido um
    único score opaco. Cada componente fica disponível para explicar."""

    popularity: float | None = Field(default=None, ge=0, le=1)
    velocity: float | None = Field(default=None, ge=-1, le=1)
    acceleration: float | None = Field(default=None, ge=-1, le=1)
    persistence: float | None = Field(default=None, ge=0, le=1)
    saturation: float | None = Field(default=None, ge=0, le=1)
    cross_platform_spread: int | None = Field(default=None, ge=0)
    audience_fit: float | None = Field(default=None, ge=0, le=1)
    profile_fit: float | None = Field(default=None, ge=0, le=1)
    content_format_fit: float | None = Field(default=None, ge=0, le=1)
    music_role_fit: float | None = Field(default=None, ge=0, le=1)
    rights_usability: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)


class TrendSignal(BaseModel):
    """Sinal de tendência com proveniência (referência §10).

    Um sinal NUNCA autoriza uso: rights_state é dimensão separada e
    UNKNOWN/BLOCKED bloqueiam (§6/§8). Dado indisponível = None/UNKNOWN —
    nunca fabricado (§14).
    """

    trend_signal_id: str
    source_platform: str  # instagram | facebook | youtube | tiktok | kwai
    source_id: str | None = None
    detected_at: datetime
    observed_at: datetime
    region: str | None = None
    category: str | None = None
    music_reference: str | None = None  # referência declarada da fonte
    music_dna: MusicDNA | None = None
    components: TrendComponents = Field(default_factory=TrendComponents)
    rights_state: RightsState = "UNKNOWN"
    rights_note: str | None = None
    state: TrendState | None = None
    reasons: list[str] = Field(default_factory=list)  # explicabilidade (§37)
    provenance: dict[str, Any] = Field(default_factory=dict)
    freshness_expires_at: datetime | None = None

    @property
    def is_stale(self, *, now: datetime | None = None) -> bool:
        if self.freshness_expires_at is None:
            return False
        return (now or datetime.now(self.freshness_expires_at.tzinfo or None)) > (
            self.freshness_expires_at
        )


class MusicOpportunity(BaseModel):
    """Oportunidade musical derivada de um sinal (referência §41).

    NÃO é aprovação editorial: no HIL a decisão editorial continua no
    fluxo de Opportunity humano (§42 — HIL é a autoridade).
    """

    opportunity_id: str
    trend_signal_id: str
    music_dna: MusicDNA | None = None
    platform: str | None = None
    audience: str | None = None
    language_code: str | None = None
    locale_code: str | None = None
    fit_score: float | None = Field(default=None, ge=0, le=1)
    freshness: float | None = None
    confidence: float | None = None
    rights_usability: float | None = None
    saturation: float | None = None
    rationale: str | None = None
    status: Literal["SUGGESTED", "DISMISSED", "ESCALATED_TO_EDITORIAL"] = "SUGGESTED"
    provenance: dict[str, Any] = Field(default_factory=dict)
