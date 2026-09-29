"""Worker foundation shell (`python -m apps.worker`, Doc 07 run sequence).

The full job loop with checkpoints/retries arrives at the jobs milestone
(Doc 17 step 13). Until then this verifies DB connectivity and reports pending
jobs — real, testable behavior, no invented orchestration.
"""

import sys

from sqlalchemy import select

from packages.domain.models import Job


def main() -> int:
    from packages.shared.db import SessionLocal
    from packages.shared.settings import get_settings

    settings = get_settings()
    print(f"URDIA HIL worker — env={settings.app_env}")
    try:
        with SessionLocal() as session:
            pending = session.scalar(
                select(Job.id).where(Job.status == "PENDING").limit(1)
            )
        print("database: OK")
        print(f"pending jobs: {'yes' if pending else 'none'}")
        return 0
    except Exception as exc:
        print(f"database: UNAVAILABLE ({exc.__class__.__name__})")
        print("hint: docker compose up -d postgres && alembic upgrade head")
        return 1


if __name__ == "__main__":
    sys.exit(main())
