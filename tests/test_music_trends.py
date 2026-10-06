"""Music Trend Intelligence tests (referência MusicIntelligence).

Segurança lógica sob teste (§57):
1. TRENDING != LICENSED — sinal viral com direitos UNKNOWN nunca é usável;
2. PLATFORM_LIMITED != GLOBAL;
3. UNKNOWN RIGHTS != SAFE;
4. BLOCKED != PUBLISHABLE;
5. TikTok license != YouTube license (escopo por plataforma);
6/7. language/locale != platform (coberto em test_language_propagation);
9/10. Social/HIL não criam segunda autoridade (serviço é determinístico
   e não aprova nada sozinho — portão humano em AudioService).

Além disso: fontes sem API oficial = TREND_SOURCE_UNAVAILABLE (nunca
sinal fabricado); estados de tendência são explicáveis; correlação
cross-platform é por DNA, não por nome; freshness/stale.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from packages.contracts.music import MusicDNA, TrendComponents, TrendSignal
from packages.domain.audio import MusicTrack
from packages.providers.music import (
    CatalogMusicProvider,
    StudioGatewayUnavailable,
    StudioMusicGateway,
)
from packages.providers.trend_sources import get_adapters, mark_stale
from packages.research.music_trends import MusicTrendService, correlate, derive_state
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def db():
    from packages.shared.db import SessionLocal

    session = SessionLocal()
    session.execute(__import__("sqlalchemy").text("SELECT 1"))
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def world(db):
    from packages.domain.models import Profile, Workspace

    ws = Workspace(name=f"trend-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.commit()
    return ws, profile


def _signal(**overrides) -> TrendSignal:
    now = datetime.now(UTC)
    fields = dict(
        trend_signal_id=f"sig-{uuid.uuid4().hex[:8]}",
        source_platform="tiktok",
        detected_at=now,
        observed_at=now,
        music_dna=MusicDNA(genre="cinematic", bpm=90, energy=0.3, vocal_mode="instrumental"),
        components=TrendComponents(popularity=0.3, velocity=0.7, saturation=0.2,
                                   cross_platform_spread=1),
        rights_state="UNKNOWN",
    )
    fields.update(overrides)
    return TrendSignal(**fields)


class TestLogicalSafety:
    def test_trending_is_not_licensed(self):
        """§57.1: viral NUNCA vira licença — rights_state é dimensão separada."""
        signal = _signal(components=TrendComponents(popularity=0.99, velocity=0.99))
        state, reasons = derive_state(signal)
        assert state == "RIGHTS_BLOCKED"
        assert any("TREND SIGNAL ≠ LICENSE" in r for r in reasons)

    def test_unknown_rights_never_safe(self):
        """§57.3: UNKNOWN não é publicável como seguro."""
        signal = _signal(rights_state="UNKNOWN")
        assert derive_state(signal)[0] == "RIGHTS_BLOCKED"

    def test_blocked_never_publishable(self):
        """§57.4: BLOCKED != PUBLISHABLE."""
        signal = _signal(rights_state="BLOCKED")
        assert derive_state(signal)[0] == "RIGHTS_BLOCKED"

    def test_platform_limited_requires_platform(self, db, world):
        """§57.2/§57.5: licença de TikTok não vale para YouTube."""
        ws, _profile = world
        track = MusicTrack(
            workspace_id=ws.id, title="Trilha TikTok",
            license_type="PLATFORM_SPECIFIC", license_notes="TikTok CML",
            rights_state="PLATFORM_LIMITED", allowed_platforms=["tiktok"],
        )
        db.add(track)
        db.commit()
        provider = CatalogMusicProvider()
        ok, code = provider.validate_usage(track, platform="tiktok")
        assert ok and code == "OK"
        ok, code = provider.validate_usage(track, platform="youtube")
        assert not ok and code == "MUSIC_PLATFORM_SCOPE_MISMATCH"


class TestTrendStates:
    def test_huge_saturated(self):
        signal = _signal(
            components=TrendComponents(popularity=0.95, saturation=0.9, velocity=0.1,
                                       cross_platform_spread=3),
            rights_state="LICENSED",
        )
        assert derive_state(signal)[0] == "HUGE_SATURATED"

    def test_emerging(self):
        signal = _signal(
            components=TrendComponents(popularity=0.2, velocity=0.8, saturation=0.1),
            rights_state="ORIGINAL",
        )
        assert derive_state(signal)[0] == "EMERGING"

    def test_decaying(self):
        signal = _signal(
            components=TrendComponents(popularity=0.7, velocity=-0.3, saturation=0.5),
            rights_state="LICENSED",
        )
        assert derive_state(signal)[0] == "DECAYING"

    def test_cross_platform(self):
        signal = _signal(
            components=TrendComponents(popularity=0.5, velocity=0.3, saturation=0.4,
                                       cross_platform_spread=2),
            rights_state="LICENSED",
        )
        assert derive_state(signal)[0] == "CROSS_PLATFORM"

    def test_state_is_explainable(self):
        """§37: toda decisão responde POR QUÊ."""
        signal = _signal(
            components=TrendComponents(popularity=0.2, velocity=0.8, saturation=0.1),
            rights_state="ORIGINAL",
        )
        state, reasons = derive_state(signal)
        assert state and len(reasons) >= 1 and all(reasons)


class TestSourcesHonest:
    @pytest.mark.parametrize("platform", ["instagram", "facebook", "youtube", "tiktok", "kwai"])
    def test_no_official_api_means_unavailable(self, platform):
        """§14: sem API oficial conectada → UNAVAILABLE, nunca sinal fabricado."""
        adapter = get_adapters()[platform]
        with pytest.raises(Exception, match="TREND_SOURCE_UNAVAILABLE"):
            adapter.fetch()

    def test_stale_signal_detected(self):
        """§51: tendência fora do TTL é stale — não tratada como atual."""
        signal = _signal(
            freshness_expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert mark_stale(signal) is True
        fresh = _signal(freshness_expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert mark_stale(fresh) is False


class TestCorrelation:
    def test_correlation_by_dna_not_name(self):
        """§11: correlação usa características normalizadas — o MESMO DNA
        com referências de nomes diferentes cruza plataformas."""
        dna = MusicDNA(genre="cinematic", bpm=90, energy=0.3, vocal_mode="instrumental")
        a = _signal(source_platform="tiktok", music_reference="Áudio X", music_dna=dna)
        b = _signal(source_platform="youtube", music_reference="Som totalmente diferente",
                    music_dna=dna.model_copy())
        groups = correlate([a, b])
        assert len(groups) == 1
        assert len(list(groups.values())[0]) == 2

    def test_different_dna_does_not_correlate(self):
        a = _signal(source_platform="tiktok",
                    music_dna=MusicDNA(genre="cinematic", bpm=90, energy=0.3,
                                       vocal_mode="instrumental"))
        b = _signal(source_platform="youtube",
                    music_dna=MusicDNA(genre="edm", bpm=140, energy=0.9,
                                       vocal_mode="instrumental"))
        assert correlate([a, b]) == {}


class TestIngest:
    def test_ingest_reports_unavailable_and_persists_nothing(self, db, world):
        ws, profile = world
        ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
        service = MusicTrendService(db)
        result = service.ingest_from_platform(ctx, "tiktok")
        assert result["status"] == "TREND_SOURCE_UNAVAILABLE"
        assert result["ingested"] == 0
        assert service.list_signals(ws.id) == []

    def test_ingest_rejects_unknown_platform(self, db, world):
        ws, profile = world
        ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
        service = MusicTrendService(db)
        with pytest.raises(Exception, match="plataforma"):
            service.ingest_from_platform(ctx, "myspace")


class TestStudioGateway:
    def test_gateway_reports_unavailable_honestly(self):
        """§25/§43: contrato existe; disponibilidade real NÃO é inventada."""
        gateway = StudioMusicGateway()
        with pytest.raises(StudioGatewayUnavailable, match="STUDIO_GATEWAY_UNAVAILABLE"):
            gateway.get_music_plan("plan-1")
        with pytest.raises(StudioGatewayUnavailable):
            gateway.get_music_asset("asset-1")
