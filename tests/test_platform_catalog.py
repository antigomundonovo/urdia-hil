"""Platform catalog + manual posting kit tests (Doc 14, AMENDMENT-011).

Export tests run the FULL human flow (create → draft → QC → approve) via
the API helpers from test_rendering, then export to kwai (MANUAL) and
instagram (API) to check the kit generation contract.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.editorial import PlatformPlan
from packages.domain.enums import PublicationMethod
from packages.domain.models import Profile, Workspace
from packages.providers.platform_catalog import (
    ALLOWED_PLATFORM_KEYS,
    PLATFORM_CATALOG,
    posting_method,
)
from packages.shared.db import get_session
from tests.test_rendering import _ready_package

# --- catalog -----------------------------------------------------------------


def test_catalog_has_exactly_the_seven_owner_platforms():
    assert {p.key for p in PLATFORM_CATALOG} == {
        "instagram",
        "facebook",
        "x",
        "youtube",
        "tiktok",
        "threads",
        "kwai",
    }
    assert ALLOWED_PLATFORM_KEYS == {p.key for p in PLATFORM_CATALOG}


def test_catalog_methods_match_official_api_reality():
    assert posting_method("instagram") is PublicationMethod.API
    assert posting_method("facebook") is PublicationMethod.API
    assert posting_method("x") is PublicationMethod.API
    assert posting_method("threads") is PublicationMethod.API
    assert posting_method("tiktok") is PublicationMethod.API
    assert posting_method("youtube") is PublicationMethod.API  # video upload
    assert posting_method("kwai") is PublicationMethod.MANUAL  # no official API
    assert posting_method("desconhecida") is PublicationMethod.MANUAL


def test_every_declared_platform_is_researched_and_documented():
    for declared in PLATFORM_CATALOG:
        assert declared.researched_on is not None
        assert declared.display_name
        assert declared.requirements, f"{declared.key} sem requisitos"


def test_registry_stays_empty_by_default():
    """Doc 14: no adapter is enabled until real credentials are configured."""
    from packages.providers.platforms import platform_registry

    assert platform_registry.descriptors() == ()


# --- manual posting kit (export flow) ----------------------------------------


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
    ws = Workspace(name=f"kit-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


def _export_to(db, client, world, package_id, platform, tmp_path, monkeypatch):
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
    ws = world[0]
    if platform != "instagram":  # _ready_package already plans instagram
        from packages.domain.editorial import ContentPackage

        package = db.get(ContentPackage, uuid.UUID(package_id))
        db.add(
            PlatformPlan(
                workspace_id=ws.id,
                opportunity_id=package.opportunity_id,
                platform=platform,
                method="MANUAL",
            )
        )
        db.commit()
        # Doc 14: changing the platform plan invalidates the previous QC —
        # a new QC run is required before exporting. The opportunity is
        # already READY with HUMAN_APPROVED in the audit (approval persists);
        # run-qc revalidates the fingerprint in place.
        qced = client.post(f"/api/v1/content/{package_id}/run-qc?workspace_id={ws.id}")
        assert qced.status_code == 200, qced.text
    resp = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={ws.id}",
        json={"platform": platform},
    )
    assert resp.status_code == 200, resp.text
    return tmp_path / "exports" / resp.json()["export_path"].split("/")[-1]


def test_manual_platform_export_contains_complete_kit(
    db, client, world, tmp_path, monkeypatch
):
    package_id, _claim = _ready_package(
        db, client, world, tmp_path, monkeypatch, fmt="PHOTO_POST"
    )
    export_path = _export_to(
        db, client, world, package_id, "kwai", tmp_path, monkeypatch
    )

    kit_path = export_path / "platform_variants" / "kwai" / "MANUAL_POSTING.md"
    assert kit_path.exists()
    kit = kit_path.read_text(encoding="utf-8")
    assert "Kit de Postagem Manual — Kwai" in kit
    assert "não oferece API oficial" in kit
    assert "Bondinho de 1911" in kit  # título copiável
    assert "POST /api/v1/publications/" in kit  # confirmação no sistema
    assert "[PROBABLE]" in kit or "[POSSIBLE]" in kit  # rastreabilidade dos claims
    assert "image/" in kit  # mídias indicadas


def test_api_platform_export_has_no_manual_kit(
    db, client, world, tmp_path, monkeypatch
):
    package_id, _claim = _ready_package(
        db, client, world, tmp_path, monkeypatch, fmt="PHOTO_POST"
    )
    export_path = _export_to(
        db, client, world, package_id, "instagram", tmp_path, monkeypatch
    )
    assert not (
        export_path / "platform_variants" / "instagram" / "MANUAL_POSTING.md"
    ).exists()
    manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["platform"] == "instagram"


def test_out_of_scope_platform_fails_closed(db, client, world, tmp_path, monkeypatch):
    """Pinterest left the scope (AMENDMENT-011): export without a platform
    plan fails closed (409), never generates a bundle."""
    package_id, _claim = _ready_package(
        db, client, world, tmp_path, monkeypatch, fmt="PHOTO_POST"
    )
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
    ws = world[0]
    resp = client.post(
        f"/api/v1/content/{package_id}/export?workspace_id={ws.id}",
        json={"platform": "pinterest"},
    )
    assert resp.status_code == 409
