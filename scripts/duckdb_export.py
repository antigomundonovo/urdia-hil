"""Export an offline DuckDB snapshot for analytics (Emenda 004).

Usage:
    python scripts/duckdb_export.py artifacts/analytics.duckdb --workspace <uuid>
    python scripts/duckdb_export.py artifacts/analytics.duckdb --sql \
        "SELECT metric, sum(value) AS total FROM metric_events GROUP BY 1"
"""

import argparse
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.analytics.offline import export_snapshot, query_snapshot  # noqa: E402
from packages.shared.db import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="output (or existing) DuckDB file")
    parser.add_argument("--workspace", help="scope the export to one workspace")
    parser.add_argument(
        "--sql", help="run a read-only query against an existing snapshot"
    )
    args = parser.parse_args()

    if args.sql:
        for row in query_snapshot(args.path, args.sql):
            print(row)
        return 0

    with SessionLocal() as session:
        counts = export_snapshot(
            session,
            args.path,
            workspace_id=UUID(args.workspace) if args.workspace else None,
        )
    for table, count in counts.items():
        print(f"{table}: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
