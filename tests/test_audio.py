"""Audio / Music Intelligence tests (Emenda 014).

Regras sob teste:
- catálogo fail-closed: LICENSE_UNKNOWN nunca é seguro; track bloqueada/
  expirada/restrição de plataforma/território não é usada;
- recomendação determinística com portão humano (SUGGESTED → APPROVED);
- sem candidato válido → plano sem música (conteúdo funciona sem);
- música nunca é inventada (só track do catálogo);
- isolamento por workspace.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import get_current_user
from apps.api.main import app
from packages.domain.audio import MusicTrack
from packages.domain.models import Profile, User, Workspace, WorkspaceMember
from packages.providers.music import CatalogMusicProvider
from packages.research.audio import AudioError, AudioService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"audio-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


@pytest.fixture()
def actor(db, world):
    ws, _profile = world
    user = User(email=f"audio-{uuid.uuid4().hex[:8]}@test.com")
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def _ctx(world, actor=None):
    ws, profile = world
    return ExecutionContext(
        workspace_id=ws.id, profile_id=profile.id, actor_id=actor.id if actor else None
    )


def _track(db, world, **overrides) -> MusicTrack:
    ws, _profile = world
    fields = dict(
        workspace_id=ws.id,
        title="Trilha Teste",
        mood="cinematic",
        intensity="low",
        is_instrumental=True,
        duration_seconds=30,
        license_type="ROYALTY_FREE",
        license_notes="licença registrada",
        rights_state="LICENSED",
    )
    fields.update(overrides)
    track = MusicTrack(**fields)
    db.add(track)
    db.commit()
    return track


class TestTrackRegistration:
    def test_register_via_service_defaults_fail_closed(self, db, world, actor):
        service = AudioService(db)
        track = service.register_track(
            _ctx(world, actor), title="Mistério Sem Licença"
        )
        assert track.rights_state == "UNKNOWN"
        assert track.license_type == "LICENSE_UNKNOWN"

    def test_register_via_api(self, client, db, world, actor):
        ws, _profile = world
        resp = client.post(
            f"/api/v1/audio/tracks?workspace_id={ws.id}",
            json={"title": "Trilha API", "license_type": "ROYALTY_FREE",
                  "license_notes": "cc0", "rights_state": "LICENSED",
                  "mood": "dark_ambient", "intensity": "low",
                  "is_instrumental": True, "duration_seconds": 40},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["rights_state"] == "LICENSED"
        assert data["license_type"] == "ROYALTY_FREE"

    def test_register_vocal_language_validated(self, client, world, actor):
        ws, _profile = world
        resp = client.post(
            f"/api/v1/audio/tracks?workspace_id={ws.id}",
            json={"title": "Vocal", "music_language_code": "pt-BR"},
        )
        assert resp.status_code == 422  # locale não vale como idioma
        resp = client.post(
            f"/api/v1/audio/tracks?workspace_id={ws.id}",
            json={"title": "Vocal", "music_language_code": "pt",
                  "is_instrumental": False},
        )
        assert resp.status_code == 200, resp.text

    def test_instrumental_cannot_have_vocal_language(self, client, world, actor):
        ws, _profile = world
        resp = client.post(
            f"/api/v1/audio/tracks?workspace_id={ws.id}",
            json={"title": "X", "is_instrumental": True, "music_language_code": "pt"},
        )
        assert resp.status_code == 409


class TestRightsFailClosed:
    def test_unknown_license_is_never_safe(self, db, world):
        track = _track(db, world, license_type="LICENSE_UNKNOWN", rights_state="UNKNOWN")
        ok, reason = CatalogMusicProvider().validate_usage(track, platform="instagram")
        assert not ok and reason == "MUSIC_RIGHTS_UNKNOWN"

    def test_expired_license_rejected(self, db, world):
        track = _track(
            db, world, license_expires_at=datetime.now(UTC) - timedelta(days=1)
        )
        ok, reason = CatalogMusicProvider().validate_usage(track, platform="instagram")
        assert not ok and reason == "MUSIC_LICENSE_EXPIRED"

    def test_platform_restriction_rejected(self, db, world):
        track = _track(db, world, allowed_platforms=["tiktok"])
        ok, reason = CatalogMusicProvider().validate_usage(track, platform="instagram")
        assert not ok and reason == "MUSIC_PLATFORM_SCOPE_MISMATCH"

    def test_blocked_track_rejected(self, db, world):
        track = _track(db, world, rights_state="BLOCKED")
        ok, reason = CatalogMusicProvider().validate_usage(track, platform="instagram")
        assert not ok and reason == "MUSIC_RIGHTS_BLOCKED"

    def test_valid_track_passes(self, db, world):
        track = _track(db, world)
        ok, reason = CatalogMusicProvider().validate_usage(track, platform="instagram")
        assert ok and reason == "OK"


class TestRecommendAndGate:
    def _package(self, db, world):
        """ContentPackage real: oportunidade mínima + canonical + package."""
        from packages.domain.editorial import CanonicalContent, ContentPackage
        from packages.research.opportunity import OpportunityService

        ws, profile = world
        ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
        opp = OpportunityService(db).create(ctx, title="Oportunidade de teste")
        canonical = CanonicalContent(
            workspace_id=ws.id,
            opportunity_id=opp.id,
            language_code="pt",
            locale_code="pt-br",
        )
        db.add(canonical)
        db.flush()
        package = ContentPackage(
            workspace_id=ws.id,
            opportunity_id=opp.id,
            canonical_content_id=canonical.id,
            format="PHOTO_POST",
            language_code="pt",
            locale_code="pt-br",
        )
        db.add(package)
        db.commit()
        return package

    def test_suggest_selects_available_track(self, db, world, actor):
        package = self._package(db, world)
        _track(db, world, mood="cinematic", duration_seconds=30)
        service = AudioService(db)
        plan = service.recommend_plan(_ctx(world, actor), package, platform="instagram")
        assert plan.status == "SUGGESTED"
        assert plan.audio_mode == "MUSIC"
        assert plan.rights_state == "LICENSED"
        assert plan.layers["music"]["title"] == "Trilha Teste"
        # nunca inventa: track_id existe no catálogo
        assert db.get(MusicTrack, uuid.UUID(plan.layers["music"]["track_id"]))

    def test_no_candidate_means_no_music(self, db, world, actor):
        package = self._package(db, world)
        # só track bloqueada no workspace
        _track(db, world, rights_state="BLOCKED")
        service = AudioService(db)
        plan = service.recommend_plan(_ctx(world, actor), package, platform="instagram")
        assert plan.audio_mode == "NONE"
        assert plan.rights_state == "NO_CANDIDATE"
        assert plan.layers["music"] is None

    def test_license_rechecked_not_assumed(self, db, world, actor):
        """Track que ficou BLOCKED após o cadastro não é recomendada."""
        package = self._package(db, world)
        track = _track(db, world)
        service = AudioService(db)
        service.set_track_status(_ctx(world, actor), track.id, "BLOCKED", reason="dmca")
        plan = service.recommend_plan(_ctx(world, actor), package, platform="instagram")
        assert plan.audio_mode == "NONE"

    def test_human_gate_decision(self, db, world, actor):
        package = self._package(db, world)
        _track(db, world)
        service = AudioService(db)
        plan = service.recommend_plan(_ctx(world, actor), package, platform="instagram")
        decided = service.decide_plan(
            _ctx(world, actor), plan.id, "APPROVED", actor_id=actor.id, reason="ok"
        )
        assert decided.status == "APPROVED"
        assert decided.decided_by == actor.id
        with pytest.raises(AudioError):
            service.decide_plan(_ctx(world, actor), plan.id, "MAYBE")

    def test_vocal_language_mismatch_not_chosen(self, db, world, actor):
        package = self._package(db, world)  # conteúdo pt
        _track(db, world, is_instrumental=False, music_language_code="ja")
        service = AudioService(db)
        plan = service.recommend_plan(_ctx(world, actor), package, platform="instagram")
        assert plan.audio_mode == "NONE"

    def test_workspace_isolation(self, db, world, actor):
        package = self._package(db, world)
        other_ws = Workspace(name=f"other-{uuid.uuid4().hex[:8]}")
        db.add(other_ws)
        db.flush()
        _track(db, (other_ws, None))
        service = AudioService(db)
        plan = service.recommend_plan(_ctx(world, actor), package, platform="instagram")
        assert plan.audio_mode == "NONE"


class TestAudioApi:
    def test_suggest_and_decide_flow(self, client, db, world, actor):
        from packages.domain.editorial import CanonicalContent, ContentPackage
        from packages.research.opportunity import OpportunityService

        ws, profile = world
        _track(db, world)
        ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
        opp = OpportunityService(db).create(ctx, title="Oportunidade API de teste")
        canonical = CanonicalContent(
            workspace_id=ws.id,
            opportunity_id=opp.id,
            language_code="pt",
            locale_code="pt-br",
        )
        db.add(canonical)
        db.flush()
        package = ContentPackage(
            workspace_id=ws.id,
            opportunity_id=opp.id,
            canonical_content_id=canonical.id,
            format="CAROUSEL",
            language_code="pt",
            locale_code="pt-br",
        )
        db.add(package)
        db.commit()

        resp = client.post(
            f"/api/v1/audio/packages/{package.id}/suggest?workspace_id={ws.id}",
            json={"platform": "instagram"},
        )
        assert resp.status_code == 200, resp.text
        plan = resp.json()
        assert plan["status"] == "SUGGESTED"

        resp = client.get(
            f"/api/v1/audio/packages/{package.id}/plan?workspace_id={ws.id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == plan["id"]

        resp = client.post(
            f"/api/v1/audio/plans/{plan['id']}/decision?workspace_id={ws.id}",
            json={"decision": "APPROVED", "reason": "trinha ok"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "APPROVED"
