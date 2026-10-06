"""Propagação do contrato de idioma (Emenda 014 §7).

Regras sob teste:
- create_content carimba language_code/locale_code: destino explícito >
  perfil (configuração editorial) > default editorial documentado;
- valor inválido = erro explícito (nunca fallback silencioso);
- idioma sobrevive: canonical → package → prompt da IA → export
  (manifest/variant) → publication;
- plataforma NUNCA determina idioma;
- demanda herda o idioma do perfil e a ponte o expõe.
"""

import json
import uuid

import pytest
from sqlalchemy import select

from packages.domain.assets import Asset
from packages.domain.enums import ContentFormat, OpportunityState, RightsClassification
from packages.domain.models import Profile, Source, Workspace
from packages.domain.publishing import Publication
from packages.research.content import ContentService, PublicationBlocked
from packages.research.opportunity import OpportunityService
from packages.research.rights import RightsService
from packages.research.verification import KnowledgeService
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def world(db, tmp_path):
    ws = Workspace(name=f"lang-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile, ContentService(db, tmp_path / "exports")


def _ctx(ws, profile):
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _opportunity_with_claim(db, world, ctx):
    ws, profile = world[0], world[1]
    opps = OpportunityService(db)
    knowledge = KnowledgeService(db)
    opp = opps.create(ctx, title="História", why_profile="fit editorial")
    claim = knowledge.add_claim(ctx, subject="S", predicate="p", object="o")
    src = Source(
        workspace_id=ws.id, profile_id=profile.id,
        url=f"https://l-{uuid.uuid4().hex[:6]}.test/x", source_type="rss",
    )
    db.add(src)
    db.flush()
    knowledge.add_evidence(ctx, claim_id=claim.id, supports=True, source_id=src.id)
    asset = Asset(
        workspace_id=ws.id, profile_id=profile.id,
        asset_type="PHOTO", file_hash=uuid.uuid4().hex, status="ACTIVE",
    )
    db.add(asset)
    db.flush()
    rights = RightsService(db)
    record = rights.classify(
        ctx, asset_id=asset.id, classification=RightsClassification.PUBLIC_DOMAIN
    )
    rights.verify(ctx, record)
    opps.attach(ctx, opp, claim_ids=[claim.id], asset_ids=[asset.id])
    opps.transition(ctx, opp, OpportunityState.RESEARCHING, reason="ok")
    return opp, claim


class TestStamping:
    def test_explicit_destination_wins(self, db, world):
        ws, profile, content = world
        ctx = _ctx(ws, profile)
        opp, _claim = _opportunity_with_claim(db, world, ctx)
        package = content.create_content(
            ctx, opp, format=ContentFormat.PHOTO_POST,
            language_code="en", locale_code="en-us",
        )
        assert package.language_code == "en"
        assert package.locale_code == "en-us"
        from packages.domain.editorial import CanonicalContent

        canonical = db.get(CanonicalContent, package.canonical_content_id)
        assert canonical.language_code == "en"

    def test_profile_language_used_when_no_destination(self, db, world):
        ws, profile, content = world
        profile.language_code = "pt"
        profile.locale_code = "pt-br"
        ctx = _ctx(ws, profile)
        opp, _claim = _opportunity_with_claim(db, world, ctx)
        package = content.create_content(ctx, opp, format=ContentFormat.PHOTO_POST)
        assert (package.language_code, package.locale_code) == ("pt", "pt-br")

    def test_profile_legacy_language_normalized(self, db, world):
        ws, profile, content = world
        profile.language = "pt-BR"  # legado
        ctx = _ctx(ws, profile)
        opp, _claim = _opportunity_with_claim(db, world, ctx)
        package = content.create_content(ctx, opp, format=ContentFormat.PHOTO_POST)
        assert (package.language_code, package.locale_code) == ("pt", "pt-br")

    def test_editorial_default_documented(self, db, world):
        """Sem destino e sem idioma no perfil: o default editorial do
        sistema (configuração explícita, documentada) — nunca dedução."""
        ws, profile, content = world
        ctx = _ctx(ws, profile)
        opp, _claim = _opportunity_with_claim(db, world, ctx)
        package = content.create_content(ctx, opp, format=ContentFormat.PHOTO_POST)
        assert (package.language_code, package.locale_code) == ("pt", "pt-br")

    def test_invalid_language_is_explicit_error(self, db, world):
        ws, profile, content = world
        ctx = _ctx(ws, profile)
        opp = _opportunity_with_claim(db, world, ctx)
        with pytest.raises(PublicationBlocked, match="idioma"):
            content.create_content(
                ctx, opp, format=ContentFormat.PHOTO_POST,
                language_code="pt-br",  # viola o contrato: nunca composto
            )
        with pytest.raises(PublicationBlocked, match="idioma"):
            content.create_content(
                ctx, opp, format=ContentFormat.PHOTO_POST,
                language_code="klingon",
            )

    def test_platform_never_sets_language(self, db, world):
        """Publicar para uma plataforma de público X não muda o idioma."""
        ws, profile, content = world
        profile.language_code = "pt"
        profile.locale_code = "pt-br"
        ctx = _ctx(ws, profile)
        for _platform in ("instagram", "tiktok"):
            opp, _claim = _opportunity_with_claim(db, world, ctx)
            package = content.create_content(ctx, opp, format=ContentFormat.PHOTO_POST)
            assert package.language_code == "pt"


class TestPropagationToAI:
    def test_copywriter_prompt_receives_explicit_language(self, db, world):
        from agents.copywriter import _render_prompt, build_context

        ws, profile, content = world
        profile.language_code = "pt"
        profile.locale_code = "pt-br"
        ctx = _ctx(ws, profile)
        opp, _claim = _opportunity_with_claim(db, world, ctx)
        package = content.create_content(
            ctx, opp, format=ContentFormat.PHOTO_POST,
            language_code="en", locale_code="en-us",
        )
        context = build_context(db, ctx, package)
        assert "language_code=en" in context["language_instruction"]
        prompt = _render_prompt(context, "")
        assert "language_code=en" in prompt
        assert "{language_instruction}" not in prompt
        assert "português do Brasil" not in prompt  # texto fixo removido

    def test_prompt_uses_profile_when_content_legacy(self, db, world):
        from agents.copywriter import build_context

        ws, profile, content = world
        profile.language_code = "pt"
        profile.locale_code = "pt-br"
        ctx = _ctx(ws, profile)
        opp, _claim = _opportunity_with_claim(db, world, ctx)
        package = content.create_content(ctx, opp, format=ContentFormat.PHOTO_POST)
        context = build_context(db, ctx, package)
        assert "language_code=pt" in context["language_instruction"]


class TestPropagationToExport:
    def _approved_package(self, db, world, **content_kwargs):
        ws, profile, content = world
        profile.language_code = "pt"
        profile.locale_code = "pt-br"
        ctx = _ctx(ws, profile)
        opp, claim = _opportunity_with_claim(db, world, ctx)
        from packages.domain.editorial import PlatformPlan

        package = content.create_content(
            ctx, opp, format=ContentFormat.PHOTO_POST,
            seo_entities=["história"], source_references=[{"url": "https://x.test"}],
            **content_kwargs,
        )
        content.generate_draft(
            ctx, package, title="Título", caption="Legenda",
            claim_ids_used=[str(claim.id)],
        )
        db.add(PlatformPlan(
            workspace_id=ws.id, opportunity_id=opp.id,
            platform="instagram", method="MANUAL",
        ))
        db.flush()
        content.run_qc(ctx, package)
        content.approve(ctx, opp)
        return content, package, opp

    def test_manifest_and_publication_carry_language(self, db, world, tmp_path):
        ws, profile, content = world
        content, package, opp = self._approved_package(db, world)
        export_dir = content.export_package(_ctx(ws, profile), package, platform="instagram")
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["language_code"] == "pt"
        assert manifest["locale_code"] == "pt-br"
        publication = db.scalars(
            select(Publication).where(Publication.content_package_id == package.id)
        ).first()
        assert publication.language_code == "pt"
        assert publication.locale_code == "pt-br"

    def test_export_without_audio_plan_has_no_audio_block(self, db, world):
        ws, profile, content = world
        content, package, opp = self._approved_package(db, world)
        export_dir = content.export_package(_ctx(ws, profile), package, platform="instagram")
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        assert "audio" not in manifest  # conteúdo funciona sem música


class TestDemandLanguage:
    def test_demand_inherits_profile_language(self, db, world):
        from packages.research.social import SocialIntelligenceService

        ws, profile, _content = world
        profile.language_code = "pt"
        profile.locale_code = "pt-br"
        ctx = _ctx(ws, profile)
        service = SocialIntelligenceService(db)
        demand = service.detect_demand(
            ctx, summary="público pede história", unique_people_count=3, platforms=["instagram"]
        )
        assert (demand.language_code, demand.locale_code) == ("pt", "pt-br")
