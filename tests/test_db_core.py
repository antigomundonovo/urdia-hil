"""Critical DB tests (Doc 04): FK integrity, unique constraints, audit creation,
job checkpoints — plus schema/models parity.

Runs only when PostgreSQL+pgvector is reachable (docker compose up -d postgres);
otherwise skipped so unit CI stays green without Docker (Doc 16 CI must pass).
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from packages.domain.enums import JobType
from packages.domain.models import AuditEvent, Job, Profile, User, Workspace


@pytest.fixture(scope="module")
def db_session():
    from packages.shared.db import SessionLocal

    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not reachable — start with: docker compose up -d postgres")
    yield session
    session.rollback()
    session.close()


def test_core_tables_exist(db_session: Session):
    names = set(inspect(db_session.bind).get_table_names())
    expected = {
        "users", "workspaces", "workspace_members", "profiles", "providers",
        "capabilities", "jobs", "job_steps", "audit_events",
    }
    assert expected <= names


def test_profile_unique_per_workspace(db_session: Session):
    ws = Workspace(name="iso-test-ws")
    u = User(name="seed")
    db_session.add_all([ws, u])
    db_session.flush()  # assign ids before children reference them

    p1 = Profile(workspace_id=ws.id, key="k", name="K")
    db_session.add(p1)
    db_session.flush()

    dup = Profile(workspace_id=ws.id, key="k", name="K2")
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_job_checkpoint_roundtrip_and_audit_append(db_session: Session):
    ws = Workspace(name="job-test-ws")
    db_session.add(ws)
    db_session.flush()

    job = Job(
        workspace_id=ws.id,
        job_type=JobType.DISCOVERY_SCAN,
        status="RUNNING",
        checkpoint={"completed_steps": ["fetch", "extract", "normalize"], "next_step": "cluster"},
    )
    db_session.add(job)
    db_session.flush()

    audit = AuditEvent(
        workspace_id=ws.id,
        action="JOB_CREATED",
        entity_type="job",
        entity_id=job.id,
        new_state="RUNNING",
    )
    db_session.add(audit)
    db_session.flush()

    loaded = db_session.get(Job, job.id)
    assert loaded.checkpoint["next_step"] == "cluster"
    assert db_session.get(AuditEvent, audit.id) is not None


def test_schema_matches_models(db_session: Session):
    """The migrated DB must equal Base.metadata — no drift between migration and models."""

    from packages.shared.db import Base

    inspector = inspect(db_session.bind)
    model_tables = set(Base.metadata.tables)
    db_tables = {t for t in inspector.get_table_names() if t != "alembic_version"}
    assert model_tables == db_tables, f"table drift: {model_tables ^ db_tables}"

    for table_name in model_tables:
        model_cols = {c.name for c in Base.metadata.tables[table_name].columns}
        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        assert model_cols == db_cols, f"column drift in {table_name}: {model_cols ^ db_cols}"
