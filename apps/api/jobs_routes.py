"""Jobs endpoints (Doc 02):
GET /api/v1/jobs, GET /api/v1/jobs/{id}, POST /api/v1/jobs/{id}/retry,
POST /api/v1/jobs/{id}/cancel.

Workspace-scoped; foreign jobs return 404 (fail closed, Doc 08).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.worker.engine import JobEngine
from packages.domain.repositories import JobRepository
from packages.shared.db import get_session

router = APIRouter(prefix="/api/v1")


def _job_payload(job) -> dict:
    return {
        "id": str(job.id),
        "workspace_id": str(job.workspace_id),
        "profile_id": str(job.profile_id) if job.profile_id else None,
        "job_type": str(job.job_type),
        "status": job.status,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "checkpoint": job.checkpoint,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/jobs")
def list_jobs(
    workspace_id: UUID = Query(...),
    profile_id: UUID | None = Query(None),
    session: Session = Depends(get_session),
):
    repo = JobRepository(session)
    if profile_id is not None:
        jobs = repo.list_for_profile(workspace_id, profile_id)
    else:
        jobs = repo.list_for_workspace(workspace_id)
    return {"jobs": [_job_payload(j) for j in jobs]}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    job = JobRepository(session).get_scoped(job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_payload(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    job = JobEngine(session, handlers={}).retry_failed(job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not retryable")
    return _job_payload(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    job = JobEngine(session, handlers={}).cancel(job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not cancellable")
    return _job_payload(job)
