"""Content flow tests (Docs 16/22): QC gates, publication bypass refused,
human approval path, export manifest."""

import json
import uuid

import pytest

from packages.domain.assets import Asset
from packages.domain.editorial import (
    Draft,
    PlatformPlan,
)
from packages.domain.enums import (
    ContentFormat,
    OpportunityState,
    RightsClassification,
)
from packages.domain.models import Profile, Source, Workspace
from packages.research.content import ContentService, PublicationBlocked
from packages.research.opportunity import OpportunityService
from packages.research.rights import RightsService
from packages.research.verification import KnowledgeService
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def world(db, tmp_path):
    ws = Workspace(name=f"content-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile, ContentService(db, tmp_path / "exports")


def _ctx(ws, profile):
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _source(db, world) -> Source:
    ws, profile = world[0], world[1]
    src = Source(
        workspace_id=ws.id, profile_id=profile.id,
        url=f"https://f-{uuid.uuid4().hex[:6]}.test/x", source_type="rss",
    )
    db.add(src)
    db.flush()
    return src


def _verified_asset(db, world, ctx) -> Asset:
    ws, profile, _, rights = world[0], world[1], world[2], world[3] if len(world) > 3 else None
    a = Asset(
        workspace_id=ws.id, profile_id=profile.id,
        asset_type="PHOTO", file_hash=uuid.uuid4().hex, status="ACTIVE",
    )
    db.add(a)
    db.flush()
    rights = RightsService(db)
    record = rights.classify(ctx, asset_id=a.id, classification=RightsClassification.PUBLIC_DOMAIN)
    rights.verify(ctx, record)
    return a


def _package_with_verified_asset(db, world, ctx):
    ws, profile, content = world
    opps = OpportunityService(db)
    knowledge = KnowledgeService(db)
    opp = opps.create(ctx, title="História", why_profile="fit editorial")
    claim = knowledge.add_claim(ctx, subject="S", predicate="p", object="o")
    knowledge.add_evidence(ctx, claim_id=claim.id, supports=True, source_id=_source(db, world).id)
    asset = _verified_asset(db, world, ctx)
    opps.attach(ctx, opp, claim_ids=[claim.id], asset_ids=[asset.id])
    opps.transition(ctx, opp, OpportunityState.RESEARCHING, reason="ok")
    package = content.create_content(
        ctx, opp, format=ContentFormat.PHOTO_POST,
        seo_entities=["história"], source_references=[{"url": "https://x.test"}],
    )
    content.generate_draft(
        ctx, package, title="Título", caption="Legenda", claim_ids_used=[str(claim.id)]
    )
    # platform plan so PLATFORM gate/ALLOWED pass
    db.add(PlatformPlan(
        workspace_id=ws.id, opportunity_id=opp.id, platform="instagram", method="MANUAL"
    ))
    db.flush()
    return opp, package


def test_qc_blocks_without_claim_evidence(db, world):
    """Doc 16: claim without evidence → QC FAIL, never READY via bypass."""
    ws, profile, content = world
    opps = OpportunityService(db)
    knowledge = KnowledgeService(db)
    ctx = _ctx(ws, profile)
    opp = opps.create(ctx, title="Sem prova")
    claim = knowledge.add_claim(ctx, subject="S", predicate="p", object="o")  # no evidence
    opps.attach(ctx, opp, claim_ids=[claim.id])
    opps.transition(ctx, opp, OpportunityState.RESEARCHING, reason="ok")
    package = content.create_content(ctx, opp, format=ContentFormat.PHOTO_POST, seo_entities=["x"])
    content.generate_draft(ctx, package, title="T", caption="C", claim_ids_used=[str(claim.id)])

    qc = content.run_qc(ctx, package)
    assert qc["status"] == "FAIL"
    assert any("without supporting evidence" in issue for issue in qc["blocking_issues"])
    with pytest.raises(PublicationBlocked, match="requires completed QC|current passing QC"):
        content.approve(ctx, opp)


def test_approval_requires_a_passing_qc(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, _package = _package_with_verified_asset(db, world, ctx)

    with pytest.raises(PublicationBlocked, match="requires completed QC"):
        content.approve(ctx, opp)


def test_qc_full_pass_then_approve_makes_ready(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)

    qc = content.run_qc(ctx, package)
    assert qc["status"] in ("PASS", "WARNING")  # placeholders may warn, not fail
    assert qc["gates"]["evidence"] == "PASS"
    assert qc["gates"]["rights"] == "PASS"
    assert qc["gates"]["human_review"] == "REQUIRED"  # Doc 00 §22

    content.approve(ctx, opp)
    assert opp.state == OpportunityState.READY.value


def test_publication_bypass_refused_when_not_ready(db, world):
    """Doc 16 non-negotiable: draft content cannot reach the publisher."""
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    # opportunity is at QUALITY_CONTROL — NOT READY yet
    with pytest.raises(PublicationBlocked, match="gate refused"):
        content.export_package(ctx, package, platform="instagram")


def test_publication_gate_rejects_failed_latest_qc(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)

    content.run_qc(ctx, package)
    content.approve(ctx, opp)
    draft = db.query(Draft).filter_by(content_package_id=package.id).first()
    draft.claim_ids_used = []
    failed_qc = content.run_qc(ctx, package)
    assert failed_qc["status"] == "FAIL"

    with pytest.raises(PublicationBlocked, match="QC_PASSED"):
        content.export_package(ctx, package, platform="instagram")


def test_publication_gate_rejects_stale_qc_after_new_draft(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)

    content.run_qc(ctx, package)
    content.approve(ctx, opp)
    draft = db.query(Draft).filter_by(content_package_id=package.id).first()
    draft.caption = "Changed after QC"

    with pytest.raises(PublicationBlocked, match="QC_PASSED"):
        content.export_package(ctx, package, platform="instagram")


def test_draft_cannot_be_edited_after_qc_starts(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    content.run_qc(ctx, package)

    with pytest.raises(PublicationBlocked, match="cannot be edited after QC"):
        content.generate_draft(ctx, package, title="Edited", caption="Too late")


def test_export_rejects_asset_path_traversal(db, world, tmp_path):
    from packages.domain.assets import Asset
    from packages.domain.editorial import OpportunityAsset

    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    asset_id = db.query(OpportunityAsset.ref_id).filter_by(opportunity_id=opp.id).scalar()
    asset = db.get(Asset, asset_id)
    asset.storage_path = "../private.png"
    content.asset_root = tmp_path / "assets"
    qc = content.run_qc(ctx, package)

    assert qc["status"] == "FAIL"
    assert qc["gates"]["visual"] == "FAIL"
    with pytest.raises(PublicationBlocked, match="completed QC"):
        content.approve(ctx, opp)


def test_export_revalidates_asset_integrity_after_qc(db, world, tmp_path):
    import hashlib

    from packages.domain.editorial import OpportunityAsset

    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    asset_id = db.query(OpportunityAsset.ref_id).filter_by(opportunity_id=opp.id).scalar()
    asset = db.get(Asset, asset_id)
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    image_path = asset_root / f"{asset.id}.png"
    image_path.write_bytes(b"validated image")
    asset.storage_path = image_path.name
    asset.file_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    content.asset_root = asset_root

    qc = content.run_qc(ctx, package)
    assert qc["status"] in ("PASS", "WARNING")
    content.approve(ctx, opp)
    image_path.write_bytes(b"tampered image")

    with pytest.raises(PublicationBlocked, match="ASSET_FILES_VALID"):
        content.export_package(ctx, package, platform="instagram")


def test_qc_rejects_local_asset_without_hash(db, world, tmp_path):
    from packages.domain.editorial import OpportunityAsset

    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    asset_id = db.query(OpportunityAsset.ref_id).filter_by(opportunity_id=opp.id).scalar()
    asset = db.get(Asset, asset_id)
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    asset.storage_path = "image.png"
    asset.file_hash = None
    (asset_root / asset.storage_path).write_bytes(b"image without recorded integrity hash")
    content.asset_root = asset_root

    qc = content.run_qc(ctx, package)

    assert qc["status"] == "FAIL"
    assert qc["gates"]["visual"] == "FAIL"


def test_export_after_approval_creates_manifest(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)

    qc = content.run_qc(ctx, package)
    assert qc["status"] in ("PASS", "WARNING")
    content.approve(ctx, opp)

    export_dir = content.export_package(ctx, package, platform="instagram")
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "PHOTO_POST"
    assert manifest["human_approved"] is True
    assert (export_dir / "captions" / "caption.txt").exists()
    assert (export_dir / "platform_variants").exists()


def test_export_refused_when_platform_not_planned(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    content.run_qc(ctx, package)
    content.approve(ctx, opp)
    with pytest.raises(PublicationBlocked, match="PLATFORM_ALLOWED"):
        content.export_package(ctx, package, platform="tiktok")


def test_reject_parks_package_forever(db, world):
    ws, profile, content = world
    ctx = _ctx(ws, profile)
    opp, package = _package_with_verified_asset(db, world, ctx)
    content.run_qc(ctx, package)
    content.reject(ctx, opp, reason="não merece o feed")
    assert opp.state == OpportunityState.REJECTED.value
    with pytest.raises(PublicationBlocked):
        content.export_package(ctx, package, platform="instagram")
