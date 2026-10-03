"""Shared fixtures. DB tests skip cleanly when PostgreSQL is unreachable."""

import os
import tempfile
import uuid

import pytest
from sqlalchemy import text


def pytest_configure(config):
    """Unique basetemp per run: an external tool on this machine locks
    predictable temp dirs (WinError 5 on cleanup). A fresh path never
    conflicts."""
    if not config.option.basetemp:
        base = os.path.join(
            tempfile.gettempdir(), "urdia-pytest-runs", f"run-{uuid.uuid4().hex[:8]}"
        )
        os.makedirs(base, exist_ok=True)  # pytest mkdir() does not create parents
        config.option.basetemp = base


@pytest.fixture(autouse=True)
def bypass_workspace_auth_for_legacy_route_tests():
    """Keep legacy endpoint tests focused; auth behavior has dedicated tests."""
    from apps.api.auth import require_workspace_access
    from apps.api.main import app

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_workspace_access] = lambda: None
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest.fixture()
def db():
    from packages.shared.db import SessionLocal

    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        # purge stale PENDING/RUNNING jobs from previous committed runs so
        # claim_next() stays deterministic (job_steps cascade via FK)
        session.execute(
            text(
                "DELETE FROM job_steps WHERE job_id IN "
                "(SELECT id FROM jobs WHERE status IN ('PENDING','RUNNING'))"
            )
        )
        session.execute(text("DELETE FROM jobs WHERE status IN ('PENDING','RUNNING')"))
        session.commit()
    except Exception:
        pytest.skip("PostgreSQL not reachable — start with: docker compose up -d postgres")
    yield session
    session.rollback()
    session.close()
