"""Domain rules and entities (Doc 01). Importing this package registers ALL
ORM models on the shared Base.metadata (needed by Alembic and the parity test)."""

from packages.domain import assets, editorial, knowledge, models, publishing  # noqa: F401
