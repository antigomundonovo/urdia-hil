"""Health endpoint (Doc 07) — no DB required; DEGRADED path when DB is down."""

from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_returns_200_and_valid_state():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"HEALTHY", "DEGRADED"}
