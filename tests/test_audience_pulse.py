"""Audience Pulse & Demand Bridge tests (UHL-5)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.models import Profile, Workspace
from packages.domain.publishing import Comment
from packages.research.social import SocialIntelligenceService
from packages.shared.db import get_session


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
    ws = Workspace(name=f"pulse-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


def _ctx(world):
    from packages.shared.execution_context import ExecutionContext
    ws, profile = world
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def test_compute_pulse(db, world):
    comment = Comment(workspace_id=world[0].id, profile_id=world[1].id, author_ref="u1", text="Great content!", intent="POSITIVE", qualified_signal="positive")
    db.add(comment)
    db.commit()
    service = SocialIntelligenceService(db)
    pulse = service.compute_pulse(_ctx(world), period_start=comment.created_at, period_end=comment.created_at)
    assert pulse.id is not None
    assert pulse.sentiment_score > 0


def test_detect_demand(db, world):
    service = SocialIntelligenceService(db)
    demand = service.detect_demand(
        _ctx(world),
        summary="Demand for X",
        unique_people_count=10,
        platforms=["instagram"],
        evidence={"source": "comments"},
    )
    assert demand.id is not None
    assert demand.summary == "Demand for X"


def test_export_demand_for_studio(db, world):
    service = SocialIntelligenceService(db)
    demand = service.detect_demand(_ctx(world), summary="X demand", unique_people_count=5, platforms=["instagram"])
    exported = service.export_demand_for_studio(_ctx(world), demand.id)
    assert exported["summary"] == "X demand"
    assert exported["unique_people_count"] == 5


def test_api_demand_endpoint(client, db, world):
    service = SocialIntelligenceService(db)
    service.detect_demand(_ctx(world), summary="API demand", unique_people_count=3, platforms=["instagram"])
    resp = client.get(f"/api/v1/social/audience/demand?workspace_id={world[0].id}&profile_id={world[1].id}")
    assert resp.status_code == 200
    assert any(d["summary"] == "API demand" for d in resp.json())


def test_api_pulse_endpoint(client, db, world):
    comment = Comment(workspace_id=world[0].id, profile_id=world[1].id, author_ref="u2", text="Nice!", intent="POSITIVE", qualified_signal="good")
    db.add(comment)
    db.commit()
    service = SocialIntelligenceService(db)
    pulse = service.compute_pulse(_ctx(world), period_start=comment.created_at, period_end=comment.created_at)
    resp = client.get(f"/api/v1/social/audience/pulse?workspace_id={world[0].id}&profile_id={world[1].id}")
    assert resp.status_code == 200
    assert resp.json()["sentiment_score"] == pulse.sentiment_score
