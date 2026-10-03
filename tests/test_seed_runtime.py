"""Seed startup validation tests."""

import pytest

from scripts.seed import ensure_database_is_ready


def test_ensure_database_is_ready_raises_clear_message_when_postgres_is_unavailable(monkeypatch):
    class FakeSession:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("scripts.seed.SessionLocal", lambda: FakeSession())

    with pytest.raises(RuntimeError, match="docker compose up -d postgres"):
        ensure_database_is_ready()
