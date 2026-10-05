"""Offline DuckDB analytical snapshots (Emenda 004, V2)."""

from pathlib import Path
from uuid import uuid4

import pytest

from packages.analytics.offline import EXPORTABLE, export_snapshot, query_snapshot
from packages.domain.models import AuditEvent
from packages.domain.publishing import Comment


@pytest.fixture()
def seeded(db):
    from packages.domain.models import Workspace

    workspace = Workspace(name="Offline Analytics WS")
    db.add(workspace)
    db.flush()
    db.add(
        Comment(
            workspace_id=workspace.id,
            author_ref="@fan",
            text="conta a história do bondinho de 1912",
            intent="SOURCE_REQUEST",
        )
    )
    db.add(
        AuditEvent(
            workspace_id=workspace.id,
            action="MACHINE_CLIENT_CREATED",
            entity_type="test",
        )
    )
    db.commit()
    return workspace.id


def test_export_and_query_snapshot(db, seeded, tmp_path):
    out = Path(tmp_path) / "snapshot.duckdb"
    counts = export_snapshot(db, out, workspace_id=seeded)
    assert counts["comments"] >= 1
    assert counts["audit_events"] >= 1

    rows = query_snapshot(
        out,
        f"SELECT author_ref, intent FROM comments WHERE workspace_id = '{seeded}'",
    )
    assert rows == [
        {"author_ref": "@fan", "intent": "SOURCE_REQUEST"}
    ]

    # Fresh export replaces the file entirely (immutable snapshots).
    counts2 = export_snapshot(db, out, workspace_id=uuid4())
    assert counts2["comments"] == 0


def test_unknown_table_rejected(db, tmp_path):
    with pytest.raises(ValueError, match="not exportable"):
        export_snapshot(db, Path(tmp_path) / "x.duckdb", tables=("users",))


def test_exportable_allowlist_is_append_only_analytical():
    assert set(EXPORTABLE) == {
        "metric_events",
        "audit_events",
        "publications",
        "comments",
    }
