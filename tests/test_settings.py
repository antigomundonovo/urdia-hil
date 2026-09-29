"""Settings composition (Doc 07 variables; secrets never logged/repr'd)."""

from packages.shared.settings import Settings


def test_database_url_composed_when_placeholder_unresolved():
    s = Settings(
        postgres_user="urdia", postgres_password="secret", _env_file=None
    )
    assert s.effective_database_url == "postgresql+psycopg://urdia:secret@localhost:5432/urdia"


def test_database_url_placeholder_is_not_used_literally():
    s = Settings(
        database_url="postgresql+psycopg://urdia:${POSTGRES_PASSWORD}@localhost:5432/urdia",
        postgres_password="real",
        _env_file=None,
    )
    assert "${" not in s.effective_database_url
    assert s.effective_database_url.endswith("@localhost:5432/urdia")


def test_password_not_in_repr():
    s = Settings(postgres_password="topsecret", _env_file=None)
    assert "topsecret" not in repr(s)


def test_execution_context_fields_doc01():
    from packages.shared.execution_context import ExecutionContext

    ctx = ExecutionContext(workspace_id="00000000-0000-0000-0000-000000000001")
    assert ctx.profile_id is None
    assert ctx.capability is None
