"""Offline analytical layer (Emenda 004, V2): DuckDB read-only snapshots.

The canonical store remains PostgreSQL (Doc 04). This module exports
append-only analytical tables (metric_events, audit_events, …) into a
single DuckDB file that analytics/BI can query without touching the
production database. Read-only by construction: the export never writes
back to PostgreSQL.

Usage:
    from packages.analytics.offline import export_snapshot, query_snapshot
    export_snapshot(out_path, workspace_id=...)   # full copy of scoped tables
    rows = query_snapshot(out_path, "SELECT metric, sum(value) FROM metric_events GROUP BY 1")
"""

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import AuditEvent
from packages.domain.publishing import Comment, MetricEvent, Publication

# Allowlist of exportable tables: append-only analytical data only.
# Anything transactional or secret stays out of the snapshot.
EXPORTABLE = {
    "metric_events": MetricEvent,
    "audit_events": AuditEvent,
    "publications": Publication,
    "comments": Comment,
}

SCHEMA = {
    "metric_events": """
        CREATE TABLE metric_events (
            id VARCHAR, publication_id VARCHAR, metric VARCHAR,
            value DOUBLE, collected_at TIMESTAMP
        )
    """,
    "audit_events": """
        CREATE TABLE audit_events (
            id VARCHAR, workspace_id VARCHAR, profile_id VARCHAR,
            actor_id VARCHAR, action VARCHAR, entity_type VARCHAR,
            entity_id VARCHAR, previous_state VARCHAR, new_state VARCHAR,
            reason VARCHAR, timestamp TIMESTAMP
        )
    """,
    "publications": """
        CREATE TABLE publications (
            id VARCHAR, workspace_id VARCHAR, profile_id VARCHAR,
            platform VARCHAR, status VARCHAR,
            created_at TIMESTAMP
        )
    """,
    "comments": """
        CREATE TABLE comments (
            id VARCHAR, workspace_id VARCHAR, profile_id VARCHAR,
            publication_id VARCHAR, author_ref VARCHAR, text VARCHAR,
            intent VARCHAR, qualified_signal VARCHAR, created_at TIMESTAMP
        )
    """,
}


def _rows(session: Session, model, workspace_id: UUID | None) -> list[dict]:
    stmt = select(model)
    if workspace_id is not None and hasattr(model, "workspace_id"):
        stmt = stmt.where(model.workspace_id == workspace_id)
    return [
        {
            c: _plain(getattr(row, c))
            for c in SCHEMA_KEYS[model.__tablename__]
            if hasattr(row, c)
        }
        for row in session.scalars(stmt).all()
    ]


# Which ORM columns feed which DuckDB column, per table.
SCHEMA_KEYS = {
    "metric_events": ["id", "publication_id", "metric", "value", "collected_at"],
    "audit_events": [
        "id", "workspace_id", "profile_id", "actor_id", "action",
        "entity_type", "entity_id", "previous_state", "new_state",
        "reason", "timestamp",
    ],
    "publications": ["id", "workspace_id", "profile_id", "platform", "status", "created_at"],
    "comments": [
        "id", "workspace_id", "profile_id", "publication_id",
        "author_ref", "text", "intent", "qualified_signal", "created_at",
    ],
}


def _plain(value):
    import datetime as _dt

    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def export_snapshot(
    session: Session,
    out_path: str | Path,
    *,
    workspace_id: UUID | None = None,
    tables: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """Export scoped tables to a fresh DuckDB file. Returns row counts.

    workspace_id=None exports every workspace — intended for the operator's
    local machine only (Doc 08: least privilege applies to files too).
    """
    import duckdb

    selected = tables or tuple(EXPORTABLE)
    unknown = set(selected) - set(EXPORTABLE)
    if unknown:
        raise ValueError(f"tables not exportable: {sorted(unknown)}")
    path = Path(out_path)
    if path.exists():
        path.unlink()  # snapshots are immutable; always a fresh file
    con = duckdb.connect(str(path))
    try:
        counts: dict[str, int] = {}
        for name in selected:
            con.execute(SCHEMA[name])
            rows = _rows(session, EXPORTABLE[name], workspace_id)
            if rows:
                cols = list(rows[0])
                placeholders = ", ".join(["?"] * len(cols))
                con.executemany(
                    f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({placeholders})",
                    [[r[c] for c in cols] for r in rows],
                )
            counts[name] = len(rows)
        return counts
    finally:
        con.close()


def query_snapshot(path: str | Path, sql: str) -> list[dict]:
    """Run a read-only query against a snapshot file."""
    import duckdb

    con = duckdb.connect(str(path), read_only=True)
    try:
        cursor = con.execute(sql)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]
    finally:
        con.close()
