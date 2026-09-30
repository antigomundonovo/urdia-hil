"""Shared fixtures. DB tests skip cleanly when PostgreSQL is unreachable."""

import pytest
from sqlalchemy import text


@pytest.fixture()
def db():
    from packages.shared.db import SessionLocal

    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not reachable — start with: docker compose up -d postgres")
    yield session
    session.rollback()
    session.close()
