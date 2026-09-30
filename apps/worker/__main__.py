"""Worker resident process (`python -m apps.worker`, Doc 07 run sequence).

Startup order (Doc 07 "Jobs"): inspect RUNNING jobs → checkpoint recovery →
then poll. `--once` processes at most one job and exits (used by tests/CI).
Ctrl+C stops gracefully.
"""

import argparse
import logging
import sys
import time

from packages.shared.db import SessionLocal


def build_handlers() -> dict:
    """Job handlers registered as milestones land (Doc 17 order).
    SOURCE_RETRIEVAL reuses the discovery scan for a single source."""
    from apps.worker.handlers import claim_verification, discovery_scan

    return {
        "DISCOVERY_SCAN": discovery_scan,
        "SOURCE_RETRIEVAL": discovery_scan,
        "CLAIM_VERIFICATION": claim_verification,
    }


def run_forever(poll_seconds: float = 2.0) -> int:
    from apps.worker.engine import JobEngine

    handlers = build_handlers()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("urdia.worker")
    log.info("worker started (poll=%ss)", poll_seconds)
    try:
        with SessionLocal() as session:
            engine = JobEngine(session, handlers)
            recovered = engine.recover_running()
            session.commit()
            if recovered:
                log.info("recovered %d RUNNING job(s) from checkpoint", recovered)

        while True:
            with SessionLocal() as session:
                engine = JobEngine(session, handlers)
                job = engine.claim_next()
                if job is None:
                    session.commit()
                    time.sleep(poll_seconds)
                    continue
                session.commit()
                log.info("running job %s (%s) attempt %s", job.id, job.job_type, job.attempt)
                engine.run_job(job)
                session.commit()
                log.info("job %s → %s", job.id, job.status)
    except KeyboardInterrupt:
        log.info("worker stopped gracefully")
        return 0


def run_once() -> int:
    from sqlalchemy import select

    from apps.worker.engine import JOB_RUNNING, JobEngine
    from packages.domain.models import Job

    handlers = build_handlers()
    with SessionLocal() as session:
        engine = JobEngine(session, handlers)
        stuck = session.scalar(select(Job.id).where(Job.status == JOB_RUNNING).limit(1))
        if stuck:
            recovered = engine.recover_running()
            session.commit()
            print(f"recovered {recovered} RUNNING job(s)")
        job = engine.claim_next()
        if job is None:
            session.commit()
            print("no pending jobs")
            return 0
        session.commit()
        engine.run_job(job)
        session.commit()
        print(f"job {job.id} → {job.status}")
        return 0 if job.status in ("SUCCEEDED", "CANCELLED") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="URDIA HIL worker")
    parser.add_argument("--once", action="store_true", help="process one cycle and exit")
    args = parser.parse_args()
    try:
        return run_once() if args.once else run_forever()
    except Exception as exc:
        print(f"worker error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        print("hint: docker compose up -d postgres && alembic upgrade head", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
