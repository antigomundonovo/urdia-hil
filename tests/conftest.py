"""Shared fixtures. DB tests skip cleanly when PostgreSQL is unreachable."""

import pytest
from sqlalchemy import text


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
