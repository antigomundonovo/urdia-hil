"""Audio / Music Intelligence routes (Emenda 014).

Catálogo de músicas + plano de áudio com PORTÃO HUMANO. Nada publica;
a decisão é sempre de humano logado (coerente com Emenda 007).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from packages.domain.audio import AudioPlan, MusicTrack
from packages.domain.models import User
from packages.multilingual import LanguageError, normalize_language_tag
from packages.research.audio import AudioError, AudioService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])


def _ctx(workspace_id: uuid.UUID, actor_id) -> ExecutionContext:
    return ExecutionContext(workspace_id=workspace_id, actor_id=actor_id)


def _track_out(track: MusicTrack) -> dict[str, Any]:
    return {
        "id": str(track.id),
        "title": track.title,
        "artist": track.artist,
        "duration_seconds": track.duration_seconds,
        "genre": track.genre,
        "mood": track.mood,
        "bpm": track.bpm,
        "is_instrumental": track.is_instrumental,
        "music_language_code": track.music_language_code,
        "music_locale_code": track.music_locale_code,
        "license_type": track.license_type,
        "license_notes": track.license_notes,
        "dna": track.dna,
        "attribution_required": track.attribution_required,
        "allowed_platforms": track.allowed_platforms,
        "allowed_territories": track.allowed_territories,
        "license_expires_at": (
            track.license_expires_at.isoformat() if track.license_expires_at else None
        ),
        "tags": track.tags,
        "intensity": track.intensity,
        "version": track.version,
        "storage_path": track.storage_path,
        "rights_state": track.rights_state,
    }


def _plan_out(plan: AudioPlan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "content_package_id": str(plan.content_package_id),
        "audio_mode": plan.audio_mode,
        "layers": plan.layers,
        "reason": plan.reason,
        "rights_state": plan.rights_state,
        "platform_constraints": plan.platform_constraints,
        "status": plan.status,
        "decided_at": plan.decided_at.isoformat() if plan.decided_at else None,
        "decision_reason": plan.decision_reason,
    }


class TrackBody(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    artist: str | None = Field(default=None, max_length=255)
    duration_seconds: int | None = Field(default=None, ge=0)
    genre: str | None = Field(default=None, max_length=64)
    mood: str | None = Field(default=None, max_length=64)
    bpm: float | None = Field(default=None, ge=0)
    is_instrumental: bool | None = None
    music_language_code: str | None = None
    music_locale_code: str | None = None
    dna: dict | None = None
    origin: str | None = Field(default=None, max_length=255)
    license_type: str | None = None
    license_notes: str | None = None
    attribution_required: bool | None = None
    allowed_platforms: list[str] | None = None
    allowed_territories: list[str] | None = None
    license_expires_at: str | None = None
    tags: list[str] | None = None
    intensity: str | None = None
    version: str | None = None
    storage_path: str | None = None
    rights_state: str | None = None


class TrackStatusBody(BaseModel):
    status: str
    reason: str | None = None


class SuggestBody(BaseModel):
    platform: str | None = None


class PlanDecisionBody(BaseModel):
    decision: str
    reason: str | None = None


@router.get("/tracks")
def list_tracks(
    workspace_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = AudioService(session)
    return [_track_out(t) for t in service.list_tracks(workspace_id)]


@router.post("/tracks")
def register_track(
    body: TrackBody,
    workspace_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    fields = body.model_dump(exclude_none=False)
    if fields.get("music_language_code"):
        # idioma da MÚSICA (letra) — canônico, nunca "pt-br" (referência §21)
        try:
            lang, locale = normalize_language_tag(fields["music_language_code"])
            if locale:
                raise LanguageError("music_language_code é idioma, não locale")
            fields["music_language_code"] = lang
        except LanguageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    service = AudioService(session)
    try:
        track = service.register_track(_ctx(workspace_id, current_user.id), **fields)
    except AudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _track_out(track)


@router.post("/tracks/{track_id}/status")
def change_track_status(
    track_id: uuid.UUID,
    body: TrackStatusBody,
    workspace_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = AudioService(session)
    try:
        track = service.set_track_status(
            _ctx(workspace_id, current_user.id), track_id, body.status, reason=body.reason
        )
    except AudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _track_out(track)


@router.post("/packages/{package_id}/suggest")
def suggest_plan(
    package_id: uuid.UUID,
    body: SuggestBody,
    workspace_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    from packages.domain.editorial import ContentPackage

    package = session.get(ContentPackage, package_id)
    if package is None or package.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="content package not found")
    service = AudioService(session)
    try:
        plan = service.recommend_plan(
            _ctx(workspace_id, current_user.id), package, platform=body.platform
        )
    except AudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _plan_out(plan)


@router.get("/packages/{package_id}/plan")
def get_latest_plan(
    package_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = AudioService(session)
    plan = service.latest_plan(workspace_id, package_id)
    return _plan_out(plan) if plan else None


@router.post("/plans/{plan_id}/decision")
def decide_plan(
    plan_id: uuid.UUID,
    body: PlanDecisionBody,
    workspace_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = AudioService(session)
    try:
        plan = service.decide_plan(
            _ctx(workspace_id, current_user.id),
            plan_id,
            body.decision,
            actor_id=current_user.id,
            reason=body.reason,
        )
    except AudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _plan_out(plan)
