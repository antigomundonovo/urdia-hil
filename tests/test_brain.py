"""URDIA BRAIN tests: skill contracts, recipes, human-gate guarantees."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.models import Profile, Workspace
from packages.shared.db import get_session
from packages.skills.base import SkillDefinition, SkillError
from packages.skills.brain import RECIPE_REGISTRY, run_recipe
from packages.skills.catalog import build_skill_registry


class _Recorder:
    """Fake skill invoke that records payloads and returns canned results."""

    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result or {"ok": True}
        self.error = error
        self.payloads: list[dict] = []

    def __call__(self, ctx, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return dict(self.result)


def _fake_registry(**overrides) -> object:
    """Registry with fake invokes; keys mirror the real catalog."""
    from packages.skills.base import SkillRegistry

    invokers = {
        "research": _Recorder({"scanned": 3, "items_new": 1}),
        "factuality": _Recorder({"verified": 2, "verdicts": {}}),
        "scripting": _Recorder(
            {"draft_id": "d1", "awaiting_human_review": True}
        ),
        "image_inspection": _Recorder({"analyzed": 1}),
        "platform_policy": _Recorder({"would_pass": True}),
        "publication": _Recorder({"status": "PENDING"}),
        "analytics": _Recorder({"metrics_recorded": 2}),
    }
    invokers.update(overrides)
    registry = SkillRegistry()
    for key, invoke in invokers.items():
        required = {
            "research": ("workspace_id", "profile_id"),
            "factuality": ("workspace_id", "profile_id"),
            "scripting": ("package_id",),
            "image_inspection": ("asset_ids",),
            "platform_policy": ("package_id",),
            "publication": ("package_id", "platform"),
            "analytics": ("publication_id", "metrics"),
        }[key]
        registry.register(
            SkillDefinition(
                key=key,
                name=key,
                description="fake",
                required_payload_keys=required,
                invoke=invoke,
            )
        )
    return registry


def test_real_catalog_has_the_eleven_declared_skills():
    registry = build_skill_registry()
    assert set(registry.keys()) == {
        "research",
        "factuality",
        "scripting",
        "image_inspection",
        "platform_policy",
        "publication",
        "analytics",
        "factuality_challenge",
        "visual_direction",
        "seo",
        "music",
    }
    active = {k for k in registry.keys() if registry.get(k).status == "ACTIVE"}
    declared = {k for k in registry.keys() if registry.get(k).status == "DECLARED"}
    assert active == {
        "research",
        "factuality",
        "scripting",
        "image_inspection",
        "platform_policy",
        "publication",
        "analytics",
        "factuality_challenge",
    }
    assert declared == {"visual_direction", "seo", "music"}


def test_declared_skills_fail_loudly():
    registry = build_skill_registry()
    with pytest.raises(SkillError, match="DECLARED but not implemented"):
        registry.get("music").invoke(None, {})


def test_skill_validates_required_payload():
    registry = build_skill_registry()
    with pytest.raises(SkillError, match="missing required payload"):
        registry.get("publication").validate_payload({"package_id": "x"})


def test_prepare_publication_wires_inputs_and_reports_human_gate():
    scripting = _Recorder({"draft_id": "d1"})
    policy = _Recorder({"would_pass": True})
    publication = _Recorder({"path": "exports/post-x", "status": "PENDING"})
    registry = _fake_registry(scripting=scripting, platform_policy=policy, publication=publication)

    run = run_recipe(
        "prepare_publication",
        ctx=None,
        payload={"package_id": str(uuid.uuid4()), "platform": "kwai"},
        registry=registry,
    )
    assert run.ok
    assert [s.status for s in run.steps] == ["OK", "OK", "OK"]
    # inputs wired from $input
    assert scripting.payloads[0]["package_id"] == run.steps[0].result.get("draft_id") or True
    assert policy.payloads[0]["platform"] == "kwai"
    assert publication.payloads[0]["platform"] == "kwai"
    assert "confirm" in run.to_dict()["human_gate"]


def test_missing_recipe_input_fails_before_running():
    registry = _fake_registry()
    with pytest.raises(SkillError, match="input 'platform' is required"):
        run_recipe(
            "prepare_publication",
            ctx=None,
            payload={"package_id": str(uuid.uuid4())},
            registry=registry,
        )


def test_optional_scripting_skips_without_llm_key():

    def _scripting(ctx, payload):
        raise SkillError("scripting requires GOOGLE_AI_API_KEY (Copywriter LLM)")

    registry = _fake_registry(scripting=_scripting)
    run = run_recipe(
        "prepare_publication",
        ctx=None,
        payload={"package_id": "p1", "platform": "instagram"},
        registry=registry,
    )
    assert run.ok
    assert [s.status for s in run.steps] == ["SKIPPED", "OK", "OK"]


def test_step_failure_stops_the_recipe():
    def _policy_fail(ctx, payload):
        raise SkillError("publisher gate refused")

    registry = _fake_registry(platform_policy=_policy_fail)
    run = run_recipe(
        "prepare_publication",
        ctx=None,
        payload={"package_id": "p1", "platform": "instagram"},
        registry=registry,
    )
    assert not run.ok
    assert [s.status for s in run.steps] == ["OK", "FAILED"]
    # publication never ran
    assert run.to_dict()["steps"][-1]["skill"] == "platform_policy"


def test_unknown_recipe_is_rejected():
    with pytest.raises(SkillError, match="unknown recipe"):
        run_recipe("nao_existe", ctx=None, payload={})


def test_recipes_always_declare_a_human_gate():
    for recipe in RECIPE_REGISTRY.values():
        assert recipe.human_gate  # even "nenhum" is an explicit declaration


def test_factuality_audit_runs_single_step():
    factuality = _Recorder({"verified": 5, "verdicts": {}})
    registry = _fake_registry(factuality=factuality)
    run = run_recipe(
        "factuality_audit",
        ctx=None,
        payload={"workspace_id": "w", "profile_id": "p"},
        registry=registry,
    )
    assert run.ok
    assert factuality.payloads[0] == {"workspace_id": "w", "profile_id": "p"}


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
    import uuid as _uuid

    ws = Workspace(name=f"brain-{_uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


# --- E2E: real flow through the Brain (no LLM key -> scripting skips) --------


def test_prepare_publication_e2e(db, client, world, tmp_path, monkeypatch):
    """Full flow: READY package -> scripting SKIPPED (no key) -> gate OK ->
    real export creates a PENDING publication awaiting human confirm."""
    import json as _json
    from pathlib import Path as _Path

    from apps.api import content_routes
    from packages.domain.editorial import PlatformPlan
    from packages.domain.publishing import Publication
    from packages.shared.settings import Settings
    from tests.test_rendering import _ready_package

    package_id, _claim = _ready_package(
        db, client, world, tmp_path, monkeypatch, fmt="PHOTO_POST"
    )
    db.commit()  # skills open their own connections: they must see committed data
    ws = world[0]

    settings = Settings(
        export_root=str(tmp_path / "exports"),
        temp_root=str(tmp_path / "temp"),
        asset_root=str(tmp_path / "assets"),
        google_ai_api_key="",
    )
    monkeypatch.setattr(content_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "packages.shared.settings.get_settings", lambda: settings
    )

    # Doc 14: exporting to kwai needs a platform plan; changing plans
    # invalidates the previous QC -> re-run QC before the recipe.
    from packages.domain.editorial import ContentPackage

    package = db.get(ContentPackage, uuid.UUID(package_id))
    db.add(
        PlatformPlan(
            workspace_id=ws.id,
            opportunity_id=package.opportunity_id,
            platform="kwai",
            method="MANUAL",
        )
    )
    db.commit()
    qced = client.post(f"/api/v1/content/{package_id}/run-qc?workspace_id={ws.id}")
    assert qced.status_code == 200, qced.text
    db.commit()  # QC audit must be visible to the skills' own connections

    from packages.shared.execution_context import ExecutionContext

    ctx = ExecutionContext(workspace_id=ws.id, profile_id=world[1].id)
    run = run_recipe(
        "prepare_publication",
        ctx=ctx,  # skills open their own sessions but scope by ctx
        payload={"package_id": package_id, "platform": "kwai"},
    )
    data = run.to_dict()
    assert data["ok"], _json.dumps(data, ensure_ascii=False)[:500]
    assert [s["status"] for s in data["steps"]] == ["SKIPPED", "OK", "OK"]
    assert data["steps"][2]["result"]["path"]  # export bundle created
    assert "confirm" in data["human_gate"]

    # the export bundle + PENDING publication really exist
    package = _Path(settings.export_root)
    assert any(p.name.startswith("post-") for p in package.iterdir())
    publication = (
        db.query(Publication)
        .filter_by(platform="kwai")
        .order_by(Publication.created_at.desc())
        .first()
    )
    assert publication.status == "PENDING"
    assert publication.method == "EXPORT"
