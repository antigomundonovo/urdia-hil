"""Sources endpoints (Doc 02):
GET/POST /api/v1/profiles/{profile_id}/sources,
GET /api/v1/sources/{source_id},
POST /api/v1/sources/{source_id}/retrieve → queues a SOURCE_RETRIEVAL job.

All workspace-scoped; profile membership is revalidated server-side (Doc 08).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from packages.domain.enums import JobType
from packages.domain.models import Profile
from packages.domain.repositories import JobRepository, SourceRepository
from packages.shared.db import get_session

router = APIRouter(prefix="/api/v1")

ALLOWED_SOURCE_TYPES = {
    "rss", "atom", "sitemap", "search", "gdelt", "wikidata", "wikipedia",
    "openalex", "crossref", "wayback", "internet_archive", "wikimedia",
}


class SourceCreate(BaseModel):
    url: str = Field(max_length=2048)
    source_type: str
    title: str | None = Field(default=None, max_length=512)
    publisher: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=16)
    jurisdiction: str | None = Field(default=None, max_length=64)


def _source_payload(s) -> dict:
    return {
        "id": str(s.id),
        "workspace_id": str(s.workspace_id),
        "profile_id": str(s.profile_id) if s.profile_id else None,
        "url": s.url,
        "canonical_url": s.canonical_url,
        "source_type": s.source_type,
        "title": s.title,
        "publisher": s.publisher,
        "language": s.language,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _profile_scoped(session: Session, workspace_id: UUID, profile_id: UUID) -> Profile:
    profile = session.get(Profile, profile_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="profile not found in workspace")
    return profile


@router.get("/profiles/{profile_id}/sources")
def list_sources(
    profile_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    sources = SourceRepository(session).list_for_profile(workspace_id, profile_id)
    return {"sources": [_source_payload(s) for s in sources]}


@router.post("/profiles/{profile_id}/sources")
def create_source(
    profile_id: UUID,
    body: SourceCreate,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    _profile_scoped(session, workspace_id, profile_id)
    if body.source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="unknown source_type")
    source = SourceRepository(session).create(
        workspace_id,
        profile_id,
        url=body.url,
        source_type=body.source_type,
        title=body.title,
        publisher=body.publisher,
        language=body.language,
        jurisdiction=body.jurisdiction,
        canonical_url=body.url,
    )
    return _source_payload(source)


@router.get("/sources/{source_id}")
def get_source(
    source_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    source = SourceRepository(session).get_scoped(source_id, workspace_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return _source_payload(source)


@router.post("/sources/{source_id}/retrieve")
def retrieve_source(
    source_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    source = SourceRepository(session).get_scoped(source_id, workspace_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    if source.profile_id is None:
        raise HTTPException(status_code=422, detail="source has no profile scope")
    job = JobRepository(session).create(
        workspace_id,
        source.profile_id,
        job_type=JobType.SOURCE_RETRIEVAL,
        payload={
            "workspace_id": str(workspace_id),
            "profile_id": str(source.profile_id),
            "source_id": str(source_id),
        },
    )
    return {"job_id": str(job.id), "status": job.status}
