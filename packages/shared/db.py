"""Database engine/session foundation.

Conventions (Doc 04): UUID ids, TIMESTAMPTZ events, snake_case, Alembic
migrations. The application runs with a least-privilege DB user — never a
superuser at runtime (Doc 08).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from packages.shared.settings import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    return create_engine(
        url or get_settings().effective_database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
