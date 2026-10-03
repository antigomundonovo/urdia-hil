"""Tests for the urdia-enqueue ops script (Doc 03/07 job queue feeding)."""

import uuid

import pytest

from packages.domain.models import Profile, Workspace
from scripts.enqueue import enqueue


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"enq-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


def test_enqueue_creates_pending_job_with_scope_echo(db, world):
    ws, profile = world
    job = enqueue(
        db,
        job_type="DISCOVERY_SCAN",
        workspace_id=ws.id,
        profile_id=profile.id,
        payload={"source_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert job.status == "PENDING"
    assert job.payload["workspace_id"] == str(ws.id)
    assert job.payload["profile_id"] == str(profile.id)
    assert job.payload["source_id"] == "00000000-0000-0000-0000-000000000001"


def test_enqueue_rejects_unknown_job_type(db, world):
    ws, profile = world
    with pytest.raises(ValueError, match="unknown job type"):
        enqueue(
            db,
            job_type="NOT_A_JOB",
            workspace_id=ws.id,
            profile_id=profile.id,
        )


def test_enqueue_rejects_wrong_payload_shape(db, world):
    ws, profile = world
    with pytest.raises(ValueError):
        enqueue(
            db,
            job_type="QC",
            workspace_id=ws.id,
            profile_id=profile.id,
            payload=["not", "a", "dict"],  # type: ignore[arg-type]
        )
