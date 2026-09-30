"""Jobs API (Doc 02): scoped list/get, retry FAILED, cancel, 404 on foreign."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.worker.engine import JOB_FAILED, FatalJobError, JobEngine
from packages.domain.enums import JobType
from packages.domain.models import Job, Profile, Workspace
from packages.shared.db import get_session


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"jobsapi-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _failed_job(db, ws, profile) -> Job:
    job = Job(
        workspace_id=ws.id,
        profile_id=profile.id,
        job_type=JobType.DISCOVERY_SCAN,
        max_attempts=1,
    )
    db.add(job)
    db.flush()
    def boom(ctx, payload, progress):
        raise FatalJobError("boom")

    engine = JobEngine(db, {str(job.job_type): boom})
    engine.claim_next()
    engine.run_job(job)
    assert job.status == JOB_FAILED
    return job


def test_list_and_get_scoped(client, db, world):
    ws, profile = world
    job = _failed_job(db, ws, profile)

    listed = client.get(f"/api/v1/jobs?workspace_id={ws.id}").json()["jobs"]
    assert any(j["id"] == str(job.id) for j in listed)

    got = client.get(f"/api/v1/jobs/{job.id}?workspace_id={ws.id}")
    assert got.status_code == 200
    assert got.json()["status"] == "FAILED"

    assert client.get(f"/api/v1/jobs/{job.id}?workspace_id={uuid.uuid4()}").status_code == 404


def test_retry_endpoint_then_cancel(client, db, world):
    ws, profile = world
    job = _failed_job(db, ws, profile)

    retried = client.post(f"/api/v1/jobs/{job.id}/retry?workspace_id={ws.id}")
    assert retried.status_code == 200
    assert retried.json()["status"] == "PENDING"

    cancelled = client.post(f"/api/v1/jobs/{job.id}/cancel?workspace_id={ws.id}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    # SUCCEEDED jobs cannot be cancelled; foreign workspace gets 404
    ghost = uuid.uuid4()
    resp = client.post(f"/api/v1/jobs/{job.id}/cancel?workspace_id={ghost}")
    assert resp.status_code == 404
