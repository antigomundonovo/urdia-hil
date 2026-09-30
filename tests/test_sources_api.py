"""Sources API (Doc 02): create/list scoped, unknown type rejected,
retrieve queues a SOURCE_RETRIEVAL job."""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.models import Profile, Source, Workspace
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
    ws = Workspace(name=f"srcapi-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def test_create_and_list_sources(client, db, world):
    ws, profile = world
    created = client.post(
        f"/api/v1/profiles/{profile.id}/sources?workspace_id={ws.id}",
        json={
            "url": "https://arquivo.test/feed.xml",
            "source_type": "rss",
            "title": "Arquivo Teste",
            "language": "pt-BR",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["source_type"] == "rss"

    listed = client.get(f"/api/v1/profiles/{profile.id}/sources?workspace_id={ws.id}").json()
    assert len(listed["sources"]) == 1


def test_unknown_source_type_rejected(client, db, world):
    ws, profile = world
    resp = client.post(
        f"/api/v1/profiles/{profile.id}/sources?workspace_id={ws.id}",
        json={"url": "https://x.test/", "source_type": "tiktok_scraper"},
    )
    assert resp.status_code == 422


def test_profile_of_other_workspace_404(client, db, world):
    ws, profile = world
    ghost = uuid.uuid4()
    resp = client.get(f"/api/v1/profiles/{profile.id}/sources?workspace_id={ghost}")
    assert resp.status_code == 404


def test_get_source_scoped(client, db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id, profile_id=profile.id, url="https://a.test/feed", source_type="rss"
    )
    db.add(source)
    db.flush()
    assert client.get(f"/api/v1/sources/{source.id}?workspace_id={ws.id}").status_code == 200
    assert client.get(f"/api/v1/sources/{source.id}?workspace_id={uuid.uuid4()}").status_code == 404


def test_retrieve_queues_job(client, db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id, profile_id=profile.id, url="https://a.test/feed", source_type="rss"
    )
    db.add(source)
    db.flush()
    resp = client.post(f"/api/v1/sources/{source.id}/retrieve?workspace_id={ws.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING"
    job_id = uuid.UUID(body["job_id"])

    job = client.get(f"/api/v1/jobs/{job_id}?workspace_id={ws.id}").json()
    assert job["job_type"] == "SOURCE_RETRIEVAL"
    assert job["payload"]["source_id"] == str(source.id)


def test_retrieve_rejects_declared_but_unimplemented_adapter(client, db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url="https://archive.test/query",
        source_type="search",
    )
    db.add(source)
    db.flush()

    response = client.post(
        f"/api/v1/sources/{source.id}/retrieve?workspace_id={ws.id}"
    )

    assert response.status_code == 422
    assert "not implemented" in response.json()["detail"]
