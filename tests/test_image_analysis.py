"""IMAGE_ANALYSIS integration tests (Doc 10): hashes + AI-proposed
classification with a FAKE vision provider (no key spend, no network)."""

import hashlib
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from apps.worker import handlers_real
from apps.worker.engine import JOB_FAILED, JOB_SUCCEEDED, JobEngine
from packages.domain.assets import Asset
from packages.domain.models import Profile, Workspace


class DummySession:
    def flush(self):
        pass

    def commit(self):
        pass

    def add(self, obj):
        pass

    def get(self, model, key):
        return None


class FakeVisionProvider:
    key = "fake"

    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result or {}
        self.error = error
        self.calls = []

    def call(self, capability_key: str, payload: dict) -> dict:
        self.calls.append((capability_key, payload))
        if self.error is not None:
            raise self.error
        return self.result


def _vision_result(classification="RESTORED", description="Foto histórica", confidence=80):
    data = {
        "visual_classification": classification,
        "description": description,
        "confidence": confidence,
    }
    return {"text": "json", "json": data, "provider": "fake", "model": "fake-model"}


def _png_bytes(color=(90, 60, 30), size=(320, 400)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def vision_world(db, tmp_path, monkeypatch):
    """Workspace + profile + asset_root pointed at tmp_path. Returns
    (workspace, profile, make_asset)."""
    ws = Workspace(name=f"vis-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()

    from packages.shared.settings import Settings

    monkeypatch.setattr(
        "packages.shared.settings.get_settings",
        lambda: Settings(
            asset_root=str(tmp_path),
            export_root=str(tmp_path / "exports"),
            google_ai_api_key="",
        ),
    )
    originals = tmp_path / "originals"
    originals.mkdir(parents=True, exist_ok=True)

    def make_asset(content: bytes) -> Asset:
        asset = Asset(
            workspace_id=ws.id,
            profile_id=profile.id,
            asset_type="PHOTO",
            status="ACTIVE",
        )
        db.add(asset)
        db.flush()
        asset.storage_path = f"originals/{asset.id}.png"
        asset.file_hash = hashlib.sha256(content).hexdigest()
        (originals / f"{asset.id}.png").write_bytes(content)
        db.commit()
        return asset

    db.expire_all()
    return ws, profile, make_asset


def _run_image_analysis(ws, profile, asset_id, *, max_attempts=1) -> SimpleNamespace:
    handlers = {"IMAGE_ANALYSIS": handlers_real.IMAGE_ANALYSIS}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        profile_id=profile.id,
        job_type="IMAGE_ANALYSIS",
        payload={"asset_ids": [str(asset_id)]},
        checkpoint={"completed_steps": [], "next_step": None},
        status="RUNNING",
        attempt=1,
        max_attempts=max_attempts,
        result=None,
        finished_at=None,
        error=None,
    )
    return JobEngine(DummySession(), handlers).run_job(job)


def test_image_analysis_records_hashes_and_classification(db, vision_world):
    ws, profile, make_asset = vision_world
    asset = make_asset(_png_bytes(color=(10, 20, 30)))
    fake = FakeVisionProvider(result=_vision_result())
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(handlers_real, "_vision_provider", lambda: fake)
        job = _run_image_analysis(ws, profile, asset.id)
    finally:
        monkeypatch.undo()

    assert job.status == JOB_SUCCEEDED, job.error
    entry = job.result["assets"][0]
    assert entry["perceptual_hash"]
    assert entry["ai_classification"]["visual_classification"] == "RESTORED"
    assert job.result["classification_is_proposal"] is True
    # first vision call carried the image inline
    capability, payload = fake.calls[0]
    assert capability == "llm.vision"
    assert payload["images"][0]["mime_type"] == "image/png"

    db.expire_all()
    stored = db.get(Asset, asset.id)
    assert stored.perceptual_hash == entry["perceptual_hash"]
    assert stored.visual_classification == "RESTORED"


def test_image_analysis_detects_duplicates(db, vision_world):
    ws, profile, make_asset = vision_world
    same_bytes = _png_bytes(color=(200, 100, 50))
    first = make_asset(same_bytes)
    second = make_asset(same_bytes)  # identical content -> same phash
    fake = FakeVisionProvider(result=_vision_result())
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(handlers_real, "_vision_provider", lambda: fake)
        # batch flow: analyze the first asset (records its phash), then the
        # second one is flagged as a duplicate of the first (Doc 10)
        job_first = _run_image_analysis(ws, profile, first.id)
        job_second = _run_image_analysis(ws, profile, second.id)
    finally:
        monkeypatch.undo()

    assert job_first.status == JOB_SUCCEEDED, job_first.error
    assert job_second.status == JOB_SUCCEEDED, job_second.error
    assert job_first.result["assets"][0]["duplicate_of"] is None
    assert job_second.result["assets"][0]["duplicate_of"] == str(first.id)


def test_image_analysis_fails_closed_on_corrupt_image(db, vision_world):
    ws, profile, make_asset = vision_world
    asset = make_asset(b"definitely not an image")
    fake = FakeVisionProvider(result=_vision_result())
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(handlers_real, "_vision_provider", lambda: fake)
        job = _run_image_analysis(ws, profile, asset.id)
    finally:
        monkeypatch.undo()

    assert job.status == JOB_FAILED
    assert "not a decodable image" in (job.error or "")


def test_image_analysis_fails_closed_on_hash_mismatch(db, vision_world, tmp_path):
    ws, profile, make_asset = vision_world
    asset = make_asset(_png_bytes(color=(1, 2, 3)))
    # tamper with the stored file, keep the DB hash — only the job can notice
    (tmp_path / asset.storage_path).write_bytes(b"tampered content")
    fake = FakeVisionProvider(result=_vision_result())
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(handlers_real, "_vision_provider", lambda: fake)
        job = _run_image_analysis(ws, profile, asset.id)
    finally:
        monkeypatch.undo()

    assert job.status == JOB_FAILED
    assert "hash mismatch" in (job.error or "")
    assert not Path(tmp_path / asset.storage_path).is_symlink()


def test_vision_provider_unavailable_is_retryable(db, vision_world):
    from packages.providers.gemini import ProviderUnavailable

    ws, profile, make_asset = vision_world
    asset = make_asset(_png_bytes(color=(5, 5, 5)))
    fake = FakeVisionProvider(error=ProviderUnavailable("rate limited"))
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(handlers_real, "_vision_provider", lambda: fake)
        # max_attempts=2 so attempt 1 gets requeued (Doc 03 retryable)
        job = _run_image_analysis(ws, profile, asset.id, max_attempts=2)
    finally:
        monkeypatch.undo()

    assert job.status == "PENDING"  # requeued, not failed
    assert "provider unavailable" in (job.error or "")
