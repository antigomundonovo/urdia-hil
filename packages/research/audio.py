"""Social Audio / Music Intelligence (Emenda 014; Doc 13).

Serviço determinístico: decide SE música é apropriada (configurável,
nunca rígida), RECOMENDA track do catálogo verificável e registra tudo
com portão humano. Nada publica; nada inventa (§29). Prefere publicar
SEM música a usar música potencialmente irregular (§21).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.audio import RIGHTS_STATES, AudioPlan, MusicTrack
from packages.domain.editorial import CanonicalContent, ContentPackage, Draft
from packages.governance.audit import append_audit
from packages.providers.music import get_music_provider
from packages.shared.execution_context import ExecutionContext

AUDIO_MODES = ("NONE", "MUSIC", "AMBIENT", "VOICE", "MUSIC_AND_VOICE")
PLAN_DECISIONS = ("APPROVED", "REJECTED")

# Códigos de erro explícitos (referência MusicIntelligence §54)
E_INVALID_LICENSE = "MUSIC_LICENSE_TYPE_INVALID"
E_INVALID_STATUS = "MUSIC_RIGHTS_STATE_INVALID"
E_TRACK_NOT_FOUND = "MUSIC_ASSET_NOT_FOUND"
E_PROVENANCE_MISSING = "MUSIC_PROVENANCE_MISSING"

# Regras editoriais determinísticas (configuráveis — não rígidas):
# palavras-chave no título/caption/ângulo → mood + intensidade.
_MOOD_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (palavras, mood, intensity)
    (
        (
            "mistério",
            "misterio",
            "enigma",
            "segredo",
            "arqueológ",
            "arqueolog",
            "sumiço",
            "desaparec",
        ),
        "dark_ambient",
        "low",
    ),
    (
        ("celebra", "aniversário", "aniversario", "festa", "conquista", "vitória", "vitoria"),
        "celebratory",
        "medium",
    ),
    (
        ("guerra", "tragédia", "tragedia", "desastre", "morte", "luto", "incêndio", "incendio"),
        "somber",
        "low",
    ),
    (
        ("curiosidade", "invenção", "invencao", "descoberta", "engenharia"),
        "curious",
        "low",
    ),
)
_DEFAULT_MOOD = "cinematic"
_DEFAULT_INTENSITY = "low"

# Duração estimada do trecho (editorial, aproximada — Doc 13 §24)
_CAROUSEL_SECONDS_PER_SLIDE = 3
_CAROUSEL_DEFAULT_SLIDES = 6
_POST_ESTIMATED_SECONDS = 15


class AudioError(Exception):
    """Rejeição explícita do plano de áudio (portão/dados inválidos)."""


class AudioService:
    def __init__(self, session: Session):
        self.session = session
        self.provider = get_music_provider()

    # --- catálogo ------------------------------------------------------------

    def register_track(self, ctx: ExecutionContext, **fields) -> MusicTrack:
        """Registra track do catálogo. rights_state nasce UNKNOWN/BLOCKED
        por padrão (fail-closed); LICENSED exige licença conhecida +
        proveniência (license_notes) declarada pelo humano."""
        license_type = fields.pop("license_type", None) or "LICENSE_UNKNOWN"
        if license_type not in {
            "ROYALTY_FREE",
            "CREATIVE_COMMONS",
            "PUBLIC_DOMAIN",
            "COMMERCIAL",
            "PLATFORM_SPECIFIC",
            "LICENSE_UNKNOWN",
        }:
            raise AudioError(f"{E_INVALID_LICENSE}: {license_type!r}")
        rights_state = fields.pop("rights_state", None)
        if rights_state is None:
            known = license_type in {"ROYALTY_FREE", "PUBLIC_DOMAIN", "CREATIVE_COMMONS"}
            rights_state = "LICENSED" if known and fields.get("license_notes") else "UNKNOWN"
        if rights_state not in RIGHTS_STATES:
            raise AudioError(f"{E_INVALID_STATUS}: {rights_state!r}")
        if fields.get("music_language_code") and fields.get("is_instrumental"):
            raise AudioError("track instrumental não tem idioma musical")
        if rights_state in {"ORIGINAL", "LICENSED"} and not fields.get("license_notes"):
            raise AudioError(
                f"{E_PROVENANCE_MISSING}: ORIGINAL/LICENSED exigem proveniência "
                "(license_notes) registrada"
            )
        track = MusicTrack(
            workspace_id=ctx.workspace_id,
            license_type=license_type,
            rights_state=rights_state,
            **fields,
        )
        self.session.add(track)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="MUSIC_TRACK_REGISTERED",
            entity_type="music_track",
            entity_id=track.id,
            new_state=rights_state,
        )
        return track

    def set_track_status(
        self,
        ctx: ExecutionContext,
        track_id: uuid.UUID,
        rights_state: str,
        *,
        reason: str | None = None,
    ) -> MusicTrack:
        if rights_state not in RIGHTS_STATES:
            raise AudioError(f"{E_INVALID_STATUS}: {rights_state!r}")
        track = self.session.get(MusicTrack, track_id)
        if track is None or track.workspace_id != ctx.workspace_id:
            raise AudioError(E_TRACK_NOT_FOUND)
        previous = track.rights_state
        track.rights_state = rights_state
        append_audit(
            self.session,
            ctx=ctx,
            action="MUSIC_TRACK_STATUS_CHANGED",
            entity_type="music_track",
            entity_id=track.id,
            previous_state=previous,
            new_state=rights_state,
            reason=reason,
        )
        return track

    def list_tracks(self, workspace_id: uuid.UUID) -> list[MusicTrack]:
        return list(
            self.session.scalars(
                select(MusicTrack)
                .where(MusicTrack.workspace_id == workspace_id)
                .order_by(MusicTrack.created_at.desc())
            )
        )

    # --- recomendação determinística ------------------------------------------

    def recommend_mood(self, text: str) -> tuple[str, str]:
        lowered = (text or "").lower()
        for words, mood, intensity in _MOOD_RULES:
            if any(word in lowered for word in words):
                return mood, intensity
        return _DEFAULT_MOOD, _DEFAULT_INTENSITY

    def _estimated_seconds(self, package: ContentPackage) -> int:
        if package.format == "CAROUSEL":
            payload = package.payload or {}
            slides = int(payload.get("slide_count") or _CAROUSEL_DEFAULT_SLIDES)
            return slides * _CAROUSEL_SECONDS_PER_SLIDE
        return _POST_ESTIMATED_SECONDS

    def recommend_plan(
        self, ctx: ExecutionContext, package: ContentPackage, *, platform: str | None = None
    ) -> AudioPlan:
        """Sugestão determinística; status=SUGGESTED até decisão humana."""
        canonical = self.session.get(CanonicalContent, package.canonical_content_id)
        draft = self.session.scalars(
            select(Draft)
            .where(Draft.content_package_id == package.id)
            .order_by(Draft.created_at.desc())
            .limit(1)
        ).first()
        text = " ".join(
            filter(
                None,
                [
                    (draft.title if draft else None),
                    (draft.caption if draft else None),
                    (canonical.editorial_angle if canonical else None),
                    (canonical.key_message if canonical else None),
                ],
            )
        )
        mood, intensity = self.recommend_mood(text)
        language_code = package.language_code
        estimated = self._estimated_seconds(package)

        candidates = self.provider.search(
            self.session,
            ctx.workspace_id,
            mood=mood,
            intensity=intensity,
            language_code=language_code,
            platform=platform,
            min_duration_seconds=estimated,
        ) or self.provider.search(
            self.session,
            ctx.workspace_id,
            language_code=language_code,
            platform=platform,
        )

        layers: dict = {"music": None, "voice": None, "ambient": None, "effects": None}
        rights_state = "NO_CANDIDATE"
        chosen: MusicTrack | None = None
        applied_mood = mood
        applied_intensity = intensity
        for track in candidates:
            ok, _reason = self.provider.validate_usage(track, platform=platform or "EXPORT")
            if not ok:
                continue
            chosen = track
            break
        if chosen is not None:
            rights_state = chosen.rights_state
            end_time = min(chosen.duration_seconds or estimated, estimated)
            layers["music"] = {
                "track_id": str(chosen.id),
                "title": chosen.title,
                "artist": chosen.artist,
                "mood": chosen.mood or mood,
                "intensity": chosen.intensity or intensity,
                "start_time": 0,
                "end_time": end_time,
                "volume": 0.2,
                "fade_in_seconds": 2,
                "fade_out_seconds": 3,
                "loop": bool(
                    package.format == "CAROUSEL"
                    and (chosen.duration_seconds or 0) < estimated
                ),
                "ducking": False,
                "instrumental": bool(chosen.is_instrumental),
                # idioma da MÚSICA ≠ idioma do conteúdo (referência §21)
                "music_language_code": chosen.music_language_code,
                "music_locale_code": chosen.music_locale_code,
                "license_type": chosen.license_type,
                "attribution_required": bool(chosen.attribution_required),
                # MusicDNA vai junto (explicabilidade, referência §9/§37)
                "dna": chosen.dna,
            }
            applied_mood = chosen.mood or mood
            applied_intensity = chosen.intensity or intensity
        reason = (
            f"Regra editorial determinística: mood={applied_mood}, "
            f"intensidade={applied_intensity}, trecho estimado={estimated}s, "
            f"idioma do conteúdo={language_code or 'não definido'}."
        )
        if chosen is None:
            reason += (
                " Nenhuma música do catálogo atendeu (direitos/idioma/duração) —"
                " conteúdo funciona SEM música (preferível a direito incerto)."
            )
        plan = AudioPlan(
            workspace_id=ctx.workspace_id,
            content_package_id=package.id,
            audio_mode="MUSIC" if chosen else "NONE",
            layers=layers,
            reason=reason,
            rights_state=rights_state,
            platform_constraints={"platform": platform, "estimated_seconds": estimated},
            status="SUGGESTED",
        )
        self.session.add(plan)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="AUDIO_PLAN_SUGGESTED",
            entity_type="audio_plan",
            entity_id=plan.id,
            new_state="SUGGESTED",
        )
        return plan

    # --- portão humano ---------------------------------------------------------

    def decide_plan(
        self,
        ctx: ExecutionContext,
        plan_id: uuid.UUID,
        decision: str,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> AudioPlan:
        if decision not in PLAN_DECISIONS:
            raise AudioError("decision must be APPROVED or REJECTED")
        plan = self.session.get(AudioPlan, plan_id)
        if plan is None or plan.workspace_id != ctx.workspace_id:
            raise AudioError(E_TRACK_NOT_FOUND)
        previous = plan.status
        plan.status = decision
        plan.decided_at = datetime.now(UTC)
        plan.decided_by = actor_id
        plan.decision_reason = reason
        append_audit(
            self.session,
            ctx=ctx,
            action="AUDIO_PLAN_DECIDED",
            entity_type="audio_plan",
            entity_id=plan.id,
            previous_state=previous,
            new_state=decision,
            reason=reason,
        )
        self.session.flush()
        return plan

    # --- consultas -------------------------------------------------------------

    def latest_plan(self, workspace_id: uuid.UUID, package_id: uuid.UUID) -> AudioPlan | None:
        return self.session.scalars(
            select(AudioPlan)
            .where(
                AudioPlan.workspace_id == workspace_id,
                AudioPlan.content_package_id == package_id,
            )
            .order_by(AudioPlan.created_at.desc())
            .limit(1)
        ).first()

    def approved_plan(self, workspace_id: uuid.UUID, package_id: uuid.UUID) -> AudioPlan | None:
        plan = self.latest_plan(workspace_id, package_id)
        if plan is not None and plan.status == "APPROVED" and plan.audio_mode != "NONE":
            return plan
        return None
