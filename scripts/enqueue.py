"""Ops tool: enqueue a validated job into the worker queue (Doc 03/07).

Jobs are created by internal routines per the constitution (there is no
POST /jobs endpoint in Doc 02) — this CLI is the operator's way to feed the
worker for batch runs (scan all sources, re-verify claims, batch QC, batch
generation proposals...). It validates the job type against the JobType
enum and stamps the payload with the workspace/profile scope so the
handlers' scope checks pass.

Usage:
  urdia-enqueue --type DISCOVERY_SCAN --workspace <uuid> --profile <uuid> \
                [--payload '{"source_id": "..."}'] [--priority 5] [--max-attempts 3]
  urdia-enqueue --list
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid as uuidlib

from packages.domain.enums import JobType
from packages.domain.models import Job
from packages.governance.audit import append_audit
from packages.shared.db import SessionLocal
from packages.shared.execution_context import ExecutionContext


def enqueue(
    session,
    *,
    job_type: str,
    workspace_id,
    profile_id,
    payload: dict | None = None,
    priority: int | None = None,
    max_attempts: int | None = None,
) -> Job:
    if job_type not in {jt.value for jt in JobType}:
        raise ValueError(f"unknown job type: {job_type}")
    ctx = ExecutionContext(workspace_id=workspace_id, profile_id=profile_id)
    stamped = dict(payload or {})
    stamped.setdefault("workspace_id", str(workspace_id))
    stamped.setdefault("profile_id", str(profile_id))
    job = Job(
        workspace_id=workspace_id,
        profile_id=profile_id,
        job_type=job_type,
        payload=stamped,
        status="PENDING",
        priority=priority,
        max_attempts=max_attempts,
    )
    session.add(job)
    session.flush()
    append_audit(
        session,
        ctx=ctx,
        action="JOB_ENQUEUED",
        entity_type="job",
        entity_id=job.id,
        new_state="PENDING",
        metadata={"job_type": job_type, "via": "urdia-enqueue"},
    )
    session.commit()
    return job


def _list_jobs(session) -> int:
    from sqlalchemy import select

    jobs = list(
        session.scalars(
            select(Job).order_by(Job.created_at.desc()).limit(20)
        )
    )
    if not jobs:
        print("no jobs")
        return 0
    print(f"{'STATUS':<10} {'TYPE':<22} {'ATTEMPT':<8} ID")
    for job in jobs:
        print(
            f"{job.status:<10} {str(job.job_type):<22} "
            f"{str(job.attempt or 0):<8} {job.id}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="URDIA job enqueue (ops)")
    parser.add_argument("--type", dest="job_type", help=f"one of: {', '.join(jt.value for jt in JobType)}")
    parser.add_argument("--workspace", help="workspace UUID")
    parser.add_argument("--profile", help="profile UUID")
    parser.add_argument("--payload", default="{}", help="JSON payload for the job")
    parser.add_argument("--priority", type=int, default=None)
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--list", action="store_true", help="list the 20 most recent jobs")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        if args.list:
            return _list_jobs(session)
        if not (args.job_type and args.workspace and args.profile):
            parser.error("--type, --workspace and --profile are required (or use --list)")
        try:
            payload = json.loads(args.payload)
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            job = enqueue(
                session,
                job_type=args.job_type,
                workspace_id=uuidlib.UUID(args.workspace),
                profile_id=uuidlib.UUID(args.profile),
                payload=payload,
                priority=args.priority,
                max_attempts=args.max_attempts,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"enqueued {job.job_type} job {job.id} (PENDING)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
