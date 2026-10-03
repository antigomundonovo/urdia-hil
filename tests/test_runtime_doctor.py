"""Runtime configuration smoke tests."""

from packages.shared.settings import Settings


def test_redacted_database_url_masks_password():
    settings = Settings(
        postgres_user="urdia",
        postgres_password="super-secret",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="urdia",
        database_url=None,
    )

    url = settings.redacted_database_url

    assert url.startswith("postgresql+psycopg://urdia:***@localhost:5432/urdia")
    assert "super-secret" not in url
    assert "***" in url
