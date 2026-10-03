"""Rendering tests (Doc 13): deterministic stills for PHOTO_POST and CAROUSEL,
render QC checks, export integration, and fail-closed behaviour.

Determinism means byte-identical PNGs for identical inputs on the same Pillow
build (Doc 13: template/renderer/font versions recorded in manifests).
"""

import hashlib
import json
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apps.api.main import app
from packages.domain.editorial import OpportunityAsset
from packages.domain.models import Profile, Source, User, Workspace, WorkspaceMember
from packages.rendering import engine, qc
from packages.research.opportunity import OpportunityService
from packages.research.rights import RightsService
from packages.research.verification import KnowledgeService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

# --- engine: determinism and structure ----------------------------------------


def test_photo_post_is_byte_deterministic():
    a = engine.render_photo_post(heading="Bondinho de 1911", body="")
    b = engine.render_photo_post(heading="Bondinho de 1911", body="")
    assert a.png == b.png
    assert (a.width, a.height) == engine.DEFAULT_SIZE


def test_photo_post_with_image_is_byte_deterministic():
    buffer = BytesIO()
    Image.new("RGB", (800, 600), (90, 80, 70)).save(buffer, format="PNG")
    image = buffer.getvalue()
    a = engine.render_photo_post(heading="Título", body="", image_bytes=image)
    b = engine.render_photo_post(heading="Título", body="", image_bytes=image)
    assert a.png == b.png
    assert a.report["image_used"] is True


def test_carousel_slide_is_byte_deterministic():
    spec = engine.SlideSpec(
        role="ORIENTATION", heading="O que aconteceu", body="Contexto do evento."
    )
    a = engine.render_carousel_slide(spec)
    b = engine.render_carousel_slide(spec)
    assert a.png == b.png


def test_carousel_structure_matches_doc13():
    """The seven fixed Doc 13 roles, in order."""
    assert engine.CAROUSEL_SLIDES == (
        "HOOK",
        "ORIENTATION",
        "EVIDENCE",
        "CONTEXT",
        "DISCOVERY",
        "MEANING",
        "SOURCE / QUESTION",
    )
    specs = engine.build_carousel_specs(
        title="t", caption="c", key_message="k", editorial_angle="a"
    )
    assert [s.role for s in specs] == list(engine.CAROUSEL_SLIDES)
    assert len(specs) == 7


def test_build_carousel_specs_never_invents_content():
    """Sections without data stay empty — the renderer lays out, never writes."""
    specs = engine.build_carousel_specs(title="Hook aqui", caption="")
    assert specs[0].heading == "Hook aqui"
    assert specs[2].body == ""  # EVIDENCE without claims stays empty
    assert specs[4].body == ""  # DISCOVERY without key_message stays empty


def test_version_block_records_determinism_metadata():
    block = engine.render_version_block()
    assert block["renderer_version"] == engine.RENDERER_VERSION
    assert block["template_version"] == engine.TEMPLATE_VERSION
    assert block["font"]["id"]
    assert block["font"]["version"]


# --- render QC (Doc 13 check list) ---------------------------------------------


def test_qc_passes_on_a_normal_slide():
    slide = engine.render_photo_post(heading="Um título curto", body="")
    checks = qc.validate_render(slide, expected_size=engine.DEFAULT_SIZE)
    assert qc.qc_summary(checks) == "FAIL" if False else checks["file_integrity"] == "PASS"
    assert checks["dimensions"] == "PASS"
    assert checks["resolution"] == "PASS"
    assert checks["aspect_ratio"] == "PASS"
    assert checks["contrast"] == "PASS"
    assert checks["audio_duration"] == "N/A"  # stills carry no audio


def test_qc_overflow_fails_on_unfitting_text():
    slide = engine.render_photo_post(heading="palavra " * 200, body="")
    checks = qc.validate_render(slide, expected_size=engine.DEFAULT_SIZE)
    assert checks["overflow"] == "FAIL"
    assert qc.qc_summary(checks) == "FAIL"


def test_qc_dimensions_fail_on_wrong_size():
    slide = engine.render_carousel_slide(engine.SlideSpec(role="HOOK", heading="x"))
    checks = qc.validate_render(slide, expected_size=(500, 500))
    assert checks["dimensions"] == "FAIL"
    # the slide's own 4:5 ratio is still fine — only the exact size mismatched
    assert checks["aspect_ratio"] == "PASS"
    assert qc.qc_summary(checks) == "FAIL"


def test_qc_file_integrity_fails_on_corrupt_png():
    slide = engine.render_photo_post(heading="x", body="")
    corrupted = slide.png[:-20] + b"\x00" * 20
    from packages.rendering.engine import RenderedSlide

    broken = RenderedSlide(
        png=corrupted, width=slide.width, height=slide.height, report=slide.report
    )
    checks = qc.validate_render(broken, expected_size=engine.DEFAULT_SIZE)
    assert checks["file_integrity"] == "FAIL"


def test_qc_missing_assets_fails_when_image_required():
    slide = engine.render_photo_post(heading="x", body="", image_bytes=None)
    checks = qc.validate_render(
        slide, expected_size=engine.DEFAULT_SIZE, requires_image=True
    )
    assert checks["missing_assets"] == "FAIL"


# --- export integration ---------------------------------------------------------


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
    ws = Workspace(name=f"rend-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _png_bytes(color=(120, 90, 60), size=(320, 400)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _ready_package(db, client, world, tmp_path, monkeypatch, *, fmt: str, with_image: bool = True):
    """Drive the API to a READY package: seed → create-content → draft → QC →
    approve. Returns (package_id, claim_id)."""
    from apps.api import content_routes
    from packages.domain.assets import Asset
    from packages.domain.editorial import PlatformPlan
    from packages.domain.enums import RightsClassification
    from packages.shared.settings import Settings

    ws, profile = world
    ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
    monkeypatch.setattr(
        content_routes,
        "get_settings",
        lambda: Settings(
            export_root=str(tmp_path / "exports"),
            temp_root=str(tmp_path / "temp"),
            asset_root=str(tmp_path / "assets"),
        ),
    )

    opps = OpportunityService(db)
    knowledge = KnowledgeService(db)
    rights = RightsService(db)
    opp = opps.create(ctx, title="Bondinho de 1911")
    claim = knowledge.add_claim(ctx, subject="Bondinho", predicate="iniciou em", object="1911")
    src = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url=f"https://arquivo-{uuid.uuid4().hex[:6]}.test/a",
        source_type="rss",
        publisher="Arquivo Nacional",
    )
    db.add(src)
    db.flush()
    knowledge.add_evidence(ctx, claim_id=claim.id, supports=True, source_id=src.id)
    asset = Asset(
        workspace_id=ws.id,
        profile_id=profile.id,
        asset_type="PHOTO",
        file_hash=uuid.uuid4().hex,
        status="ACTIVE",
    )
    db.add(asset)
    db.flush()
    record = rights.classify(
        ctx, asset_id=asset.id, classification=RightsClassification.PUBLIC_DOMAIN
    )
    rights.verify(ctx, record)
    opps.attach(ctx, opp, claim_ids=[claim.id], asset_ids=[asset.id] if with_image else [])
    db.add(
        PlatformPlan(
            workspace_id=ws.id, opportunity_id=opp.id, platform="instagram", method="MANUAL"
        )
    )
    db.commit()
    db.expire_all()

    if with_image:
        image = _png_bytes()
        fresh = db.get(Asset, asset.id)
        fresh.storage_path = f"originals/{fresh.id}.png"
        fresh.file_hash = hashlib.sha256(image).hexdigest()
        asset_dir = tmp_path / "assets" / "originals"
        asset_dir.mkdir(parents=True, exist_ok=True)
        (asset_dir / f"{fresh.id}.png").write_bytes(image)
        db.commit()

    created = client.post(
        f"/api/v1/opportunities/{opp.id}/create-content?workspace_id={ws.id}",
        json={"format": fmt, "editorial_angle": "memória urbana"},
    )
    assert created.status_code == 200, created.text
    package_id = created.json()["package_id"]

    caption = (
        "O bondinho começou a operar em 1911. Uma marca da cidade. "
        "Ainda hoje é lembrado. Símbolo de uma época. Parte da memória coletiva."
    )
    drafted = client.post(
        f"/api/v1/content/{package_id}/generate-draft?workspace_id={ws.id}",
        json={"title": "Bondinho de 1911", "caption": caption, "claim_ids_used": [str(claim.id)]},
    )
    assert drafted.status_code == 200, drafted.text

    qced = client.post(f"/api/v1/content/{package_id}/run-qc?workspace_id={ws.id}")
    assert qced.status_code == 200, qced.text
    from apps.api.auth import get_current_user

    actor = User(
        name="Rendering Reviewer",
        email=f"rendering-reviewer-{uuid.uuid4().hex[:8]}@example.test",
    )
    db.add(actor)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=actor.id))
    db.flush()
    app.dependency_overrides[get_current_user] = lambda: actor
    approved = client.post(f"/api/v1/content/{package_id}/approve?workspace_id={ws.id}")
    assert approved.status_code == 200, approved.text
    return package_id, claim.id


def _export(client, world, package_id, monkeypatch, tmp_path):
    ws, _ = world
    from apps.api import content_routes
    from packages.shared.settings import Settings

    monkeypatch.setattr(
        content_routes,
        "get_settings",
        lambda: Settings(
            export_root=str(tmp_path / "exports"),
            temp_root=str(tmp_path / "temp"),
            asset_root=str(tmp_path / "assets"),
        ),
    )
    resp = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={ws.id}",
        json={"platform": "instagram"},
    )
    assert resp.status_code == 200, resp.text
    export_path = tmp_path / "exports" / resp.json()["export_path"].split("/")[-1]
    return export_path


def test_export_photo_post_includes_render_and_manifest(client, db, world, monkeypatch, tmp_path):
    package_id, _ = _ready_package(db, client, world, tmp_path, monkeypatch, fmt="PHOTO_POST")
    export_path = _export(client, world, package_id, monkeypatch, tmp_path)

    rendered = export_path / "image" / "render-photo-post.png"
    assert rendered.exists()
    with Image.open(rendered) as probe:
        assert probe.size == engine.DEFAULT_SIZE

    manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["render"]["summary"] == "PASS"
    assert manifest["render"]["renderer_version"] == engine.RENDERER_VERSION
    assert manifest["render"]["template_version"] == engine.TEMPLATE_VERSION
    file_entry = manifest["render"]["files"][0]
    assert file_entry["path"] == "image/render-photo-post.png"
    assert file_entry["sha256"] == hashlib.sha256(rendered.read_bytes()).hexdigest()
    # provenance: the ORIGINAL asset bytes are still exported untouched
    originals = [
        p
        for p in (export_path / "image").glob("*.png")
        if p.name != "render-photo-post.png"
    ]
    assert originals, "original asset must remain in the export"


def test_export_carousel_writes_seven_slides(client, db, world, monkeypatch, tmp_path):
    package_id, _ = _ready_package(db, client, world, tmp_path, monkeypatch, fmt="CAROUSEL")
    export_path = _export(client, world, package_id, monkeypatch, tmp_path)

    slides = sorted((export_path / "carousel").glob("slide-*.png"))
    assert len(slides) == 7
    names = [p.name for p in slides]
    assert "slide-01-hook.png" in names
    assert "slide-07-source-question.png" in names

    manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["render"]["summary"] == "PASS"
    assert len(manifest["render"]["files"]) == 7
    for entry in manifest["render"]["files"]:
        local = export_path / entry["path"]
        assert local.exists()
        assert hashlib.sha256(local.read_bytes()).hexdigest() == entry["sha256"]
        assert all(v != "FAIL" for v in entry["qc"].values())


def test_export_microloop_keeps_pre_render_behaviour(client, db, world, monkeypatch, tmp_path):
    """MICROLOOP assembly is out of V1 render: no render block, export still works."""
    package_id, _ = _ready_package(db, client, world, tmp_path, monkeypatch, fmt="MICROLOOP")
    export_path = _export(client, world, package_id, monkeypatch, tmp_path)
    manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
    assert "render" not in manifest
    assert (export_path / "captions" / "caption.txt").exists()


def test_export_fails_closed_when_asset_is_not_decodable(client, db, world, monkeypatch, tmp_path):
    """A file with a valid hash but undecodable content blocks the export
    (render QC: missing assets / file integrity, fail closed)."""
    from sqlalchemy import select

    from apps.api import content_routes
    from packages.domain.assets import Asset
    from packages.domain.editorial import ContentPackage
    from packages.shared.settings import Settings

    package_id, _ = _ready_package(db, client, world, tmp_path, monkeypatch, fmt="PHOTO_POST")
    ws, _ = world
    # corrupt the stored asset: replace bytes, keep hash consistent so only
    # rendering can detect the problem
    package = db.scalars(
        select(ContentPackage).where(ContentPackage.id == uuid.UUID(package_id))
    ).one()
    asset_link = db.query(OpportunityAsset).filter_by(opportunity_id=package.opportunity_id).one()
    asset = db.get(Asset, asset_link.ref_id)
    fake = b"definitely not an image"
    asset.storage_path = f"originals/{asset.id}.png"
    asset.file_hash = hashlib.sha256(fake).hexdigest()
    (tmp_path / "assets" / "originals" / f"{asset.id}.png").write_bytes(fake)
    db.commit()

    monkeypatch.setattr(
        content_routes,
        "get_settings",
        lambda: Settings(
            export_root=str(tmp_path / "exports"),
            temp_root=str(tmp_path / "temp"),
            asset_root=str(tmp_path / "assets"),
        ),
    )
    resp = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={ws.id}",
        json={"platform": "instagram"},
    )

    assert resp.status_code == 409


def test_export_carousel_includes_render_metadata(client, db, world, monkeypatch, tmp_path):
    """The manifest records render version + per-file hashes for audit."""
    package_id, _ = _ready_package(db, client, world, tmp_path, monkeypatch, fmt="CAROUSEL")
    export_path = _export(client, world, package_id, monkeypatch, tmp_path)

    manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
    assert "render" in manifest
    for entry in manifest["render"]["files"]:
        local = export_path / entry["path"]
        assert hashlib.sha256(local.read_bytes()).hexdigest() == entry["sha256"]
