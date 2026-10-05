"""Photo import + rights gate tests (Doc 16: duplicate image, rights unknown
→ RIGHTS_BLOCKED; Doc 08: upload security, path traversal)."""

import uuid

import pytest

from packages.domain.enums import (
    RightsClassification,
    RightsGateOutcome,
    VisualClassification,
)
from packages.domain.models import Profile, Source, Workspace
from packages.research.photos import PhotoService, UploadRejected
from packages.research.rights import RightsService
from packages.shared.execution_context import ExecutionContext

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG_BYTES = b"\xff\xd8\xff" + b"1" * 64


@pytest.fixture()
def world(db, tmp_path):
    ws = Workspace(name=f"photo-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile, PhotoService(db, tmp_path), RightsService(db)


def _ctx(ws, profile):
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def test_import_photo_happy_path(db, world):
    ws, profile, photos, _ = world
    result = photos.import_photo(
        _ctx(ws, profile), content=PNG_BYTES, original_filename="praia-1920.png"
    )
    assert result.mime == "image/png"
    assert result.duplicate_of is None
    assert result.asset.visual_classification == VisualClassification.ORIGINAL_AS_RETRIEVED.value
    assert "originals" in result.asset.storage_path
    # user filename never becomes the storage path (Doc 08)
    assert "praia-1920" not in result.asset.storage_path
    assert (photos.asset_root / result.asset.storage_path).read_bytes() == PNG_BYTES


def test_import_rejects_bad_content(db, world):
    ws, profile, photos, _ = world
    with pytest.raises(UploadRejected, match="not an allowed image"):
        photos.import_photo(
            _ctx(ws, profile), content=b"<html>not an image</html>", original_filename="x.png"
        )
    with pytest.raises(UploadRejected, match="extension"):
        photos.import_photo(_ctx(ws, profile), content=PNG_BYTES, original_filename="evil.exe")
    with pytest.raises(UploadRejected, match="empty"):
        photos.import_photo(_ctx(ws, profile), content=b"")


def test_exact_duplicate_detected(db, world):
    ws, profile, photos, _ = world
    first = photos.import_photo(_ctx(ws, profile), content=PNG_BYTES)
    second = photos.import_photo(_ctx(ws, profile), content=PNG_BYTES)
    assert second.duplicate_of == first.asset.id  # Doc 16 duplicate rule


def test_assets_are_isolated_between_profiles(db, world):
    ws, profile, photos, _ = world
    other_profile = Profile(
        workspace_id=ws.id,
        key="other",
        name="Other",
    )
    db.add(other_profile)
    db.flush()
    first = photos.import_photo(_ctx(ws, profile), content=PNG_BYTES)
    second = photos.import_photo(_ctx(ws, other_profile), content=PNG_BYTES)

    assert second.duplicate_of is None
    assert photos.find_similar(_ctx(ws, other_profile), first.perceptual_hash) == []
    assert photos.get_scoped(first.asset.id, _ctx(ws, other_profile)) is None


def test_photo_import_rejects_profile_from_another_workspace(db, world):
    ws, _, photos, _ = world
    with pytest.raises(LookupError, match="profile not found"):
        photos.import_photo(
            ExecutionContext(workspace_id=ws.id, profile_id=uuid.uuid4()),
            content=PNG_BYTES,
        )


def test_rights_unknown_blocks_publication(db, world):
    """Doc 16/11: UNKNOWN → BLOCK. An asset with no record blocks too."""
    ws, profile, photos, rights = world
    result = photos.import_photo(_ctx(ws, profile), content=JPEG_BYTES)
    assert rights.evaluate(_ctx(ws, profile), result.asset.id) is RightsGateOutcome.BLOCK

    rights.classify(_ctx(ws, profile), asset_id=result.asset.id,
                    classification=RightsClassification.UNKNOWN)
    assert rights.evaluate(_ctx(ws, profile), result.asset.id) is RightsGateOutcome.BLOCK


def test_rights_prohibited_and_permission_block(db, world):
    ws, profile, photos, rights = world
    ctx = _ctx(ws, profile)
    a = photos.import_photo(ctx, content=PNG_BYTES).asset
    b = photos.import_photo(ctx, content=PNG_BYTES).asset
    rights.classify(ctx, asset_id=a.id, classification=RightsClassification.PROHIBITED)
    rights.classify(ctx, asset_id=b.id, classification=RightsClassification.PERMISSION_REQUIRED)
    assert rights.evaluate(ctx, a.id) is RightsGateOutcome.BLOCK
    assert rights.evaluate(ctx, b.id) is RightsGateOutcome.BLOCK


def test_verified_public_domain_may_proceed(db, world):
    ws, profile, photos, rights = world
    ctx = _ctx(ws, profile)
    asset = photos.import_photo(ctx, content=PNG_BYTES).asset
    record = rights.classify(
        ctx, asset_id=asset.id,
        classification=RightsClassification.PUBLIC_DOMAIN,
        confidence=90, notes="Arquivo Nacional, domínio público",
    )
    # classified but NOT verified yet → still blocked (fail closed)
    assert rights.evaluate(ctx, asset.id) is RightsGateOutcome.BLOCK

    rights.verify(ctx, record)
    assert rights.evaluate(ctx, asset.id) is RightsGateOutcome.MAY_PROCEED


def test_cc_by_verified_allows_with_attribution(db, world):
    ws, profile, photos, rights = world
    ctx = _ctx(ws, profile)
    asset = photos.import_photo(ctx, content=PNG_BYTES).asset
    record = rights.classify(
        ctx, asset_id=asset.id, classification=RightsClassification.CC_BY,
        attribution_required=True, attribution_text="Foto: Autor, 1920",
        license="CC BY 4.0",
    )
    rights.verify(ctx, record)
    assert rights.evaluate(ctx, asset.id) is RightsGateOutcome.MAY_PROCEED


def test_foreign_workspace_asset_fails_closed(db, world):
    ws, profile, photos, rights = world
    result = photos.import_photo(_ctx(ws, profile), content=PNG_BYTES)
    with pytest.raises(LookupError):
        rights.evaluate(ExecutionContext(workspace_id=uuid.uuid4()), result.asset.id)
    # scoped fetch returns None for another profile/workspace (fail-closed contract)
    assert photos.get_scoped(
        result.asset.id, ExecutionContext(workspace_id=uuid.uuid4())
    ) is None


def test_rights_operations_are_profile_scoped(db, world):
    ws, profile, photos, rights = world
    ctx = _ctx(ws, profile)
    asset = photos.import_photo(ctx, content=PNG_BYTES).asset
    record = rights.classify(
        ctx,
        asset_id=asset.id,
        classification=RightsClassification.PUBLIC_DOMAIN,
    )
    other_profile = Profile(workspace_id=ws.id, key="rights-other", name="Other")
    db.add(other_profile)
    db.flush()
    foreign_ctx = _ctx(ws, other_profile)

    with pytest.raises(LookupError):
        rights.evaluate(foreign_ctx, asset.id)
    with pytest.raises(LookupError):
        rights.latest_record(foreign_ctx, asset.id)
    with pytest.raises(LookupError):
        rights.verify(foreign_ctx, record)
    assert rights.evaluate(ctx, asset.id) is RightsGateOutcome.BLOCK


def test_rights_evidence_source_must_match_asset_profile(db, world):
    ws, profile, photos, rights = world
    asset = photos.import_photo(_ctx(ws, profile), content=PNG_BYTES).asset
    other_profile = Profile(workspace_id=ws.id, key="source-other", name="Other")
    db.add(other_profile)
    db.flush()
    source = Source(
        workspace_id=ws.id,
        profile_id=other_profile.id,
        url="https://other.test/rights",
        source_type="rss",
    )
    db.add(source)
    db.flush()

    with pytest.raises(LookupError):
        rights.classify(
            _ctx(ws, profile),
            asset_id=asset.id,
            classification=RightsClassification.PUBLIC_DOMAIN,
            evidence_source_id=source.id,
        )
