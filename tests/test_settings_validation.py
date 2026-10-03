"""Settings validation tests."""

from packages.shared.settings import Settings


def test_validation_issues_flags_missing_postgres_password():
    settings = Settings(postgres_password="", postgres_host="localhost")

    assert "POSTGRES_PASSWORD is missing or unresolved in .env" in settings.validation_issues()


def test_validation_issues_flags_unresolved_database_placeholder():
    settings = Settings(
        postgres_password="change-me",
        database_url=(
            "postgresql+psycopg://urdia:${POSTGRES_PASSWORD}@localhost:5432/urdia"
        ),
    )

    message = "DATABASE_URL still contains an unresolved environment placeholder"
    assert message in settings.validation_issues()
