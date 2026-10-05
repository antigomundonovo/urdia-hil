"""Audience Pulse & Demand Bridge tests (UHL-5)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.models import Profile, Workspace
from packages.domain.publishing import Comment
from packages.research.social import SocialError, SocialIntelligenceService
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
    comment = Comment(
        workspace_id=world[0].id,
        profile_id=world[1].id,
        author_ref="u1",
        text="Great content!",
        intent="POSITIVE",
        qualified_signal="positive",
    )
    db.add(comment)
    db.commit()
    service = SocialIntelligenceService(db)
    pulse = service.compute_pulse(
        _ctx(world),
        period_start=comment.created_at,
        period_end=comment.created_at,
    )
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
    demand = service.detect_demand(
        _ctx(world), summary="X demand", unique_people_count=5, platforms=["instagram"]
    )
    exported = service.export_demand_for_studio(_ctx(world), demand.id)
    assert exported["summary"] == "X demand"
    assert exported["unique_people_count"] == 5


def test_audience_demand_is_profile_scoped(db, world):
    ws, profile = world
    service = SocialIntelligenceService(db)
    primary = service.detect_demand(
        _ctx(world),
        summary="Primary demand",
        unique_people_count=3,
        platforms=["instagram"],
    )
    secondary = Profile(workspace_id=ws.id, key="secondary", name="Secondary")
    db.add(secondary)
    db.commit()
    from packages.shared.execution_context import ExecutionContext

    foreign_ctx = ExecutionContext(workspace_id=ws.id, profile_id=secondary.id)
    assert service.list_audience_demand(foreign_ctx) == []
    assert service.get_demand(foreign_ctx, primary.id) is None


def test_audience_pulse_is_profile_scoped(db, world):
    ws, profile = world
    service = SocialIntelligenceService(db)
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    pulse = service.compute_pulse(
        _ctx(world), now - timedelta(minutes=1), now + timedelta(minutes=1)
    )
    secondary = Profile(workspace_id=ws.id, key="secondary", name="Secondary")
    db.add(secondary)
    db.commit()
    from packages.shared.execution_context import ExecutionContext

    foreign_ctx = ExecutionContext(workspace_id=ws.id, profile_id=secondary.id)
    assert service.get_pulse(foreign_ctx, pulse.id) is None
    assert service.get_latest_audience_pulse(foreign_ctx) is None


def test_api_demand_endpoint(client, db, world):
    service = SocialIntelligenceService(db)
    service.detect_demand(
        _ctx(world), summary="API demand", unique_people_count=3, platforms=["instagram"]
    )
    resp = client.get(
        f"/api/v1/social/audience/demand?workspace_id={world[0].id}&profile_id={world[1].id}"
    )
    assert resp.status_code == 200
    assert any(d["summary"] == "API demand" for d in resp.json())


def test_api_pulse_endpoint(client, db, world):
    comment = Comment(
        workspace_id=world[0].id,
        profile_id=world[1].id,
        author_ref="u2",
        text="Nice!",
        intent="POSITIVE",
        qualified_signal="good",
    )
    db.add(comment)
    db.commit()
    service = SocialIntelligenceService(db)
    pulse = service.compute_pulse(
        _ctx(world),
        period_start=comment.created_at,
        period_end=comment.created_at,
    )
    resp = client.get(
        f"/api/v1/social/audience/pulse?workspace_id={world[0].id}&profile_id={world[1].id}"
    )
    assert resp.status_code == 200
    assert resp.json()["sentiment_score"] == pulse.sentiment_score


def test_audience_data_isolated_between_profiles(db, world):
    ws, profile_a = world
    profile_b = Profile(workspace_id=ws.id, key="second", name="Second")
    db.add(profile_b)
    db.flush()
    db.commit()

    service = SocialIntelligenceService(db)
    demand_a = service.detect_demand(
        _ctx((ws, profile_a)),
        summary="Only profile A",
        unique_people_count=7,
        platforms=["instagram"],
    )
    service.compute_pulse(
        _ctx((ws, profile_a)),
        period_start=demand_a.created_at,
        period_end=demand_a.created_at,
    )

    assert [d.id for d in service.list_audience_demand(_ctx((ws, profile_a)))] == [demand_a.id]
    assert service.list_audience_demand(_ctx((ws, profile_b))) == []
    assert service.get_latest_audience_pulse(_ctx((ws, profile_b))) is None


def test_audience_operations_require_profile_context(db, world):
    from packages.shared.execution_context import ExecutionContext
    service = SocialIntelligenceService(db)
    ctx = ExecutionContext(workspace_id=world[0].id)

    with pytest.raises(SocialError, match="profile context"):
        service.detect_demand(
            ctx,
            summary="Must be scoped",
            unique_people_count=1,
            platforms=["instagram"],
        )

    with pytest.raises(Exception, match="profile context"):
        service.compute_pulse(
            ctx,
            period_start=world[0].created_at,
            period_end=world[0].created_at,
        )
