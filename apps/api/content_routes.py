"""Content endpoints (Doc 02):
POST /api/v1/opportunities/{id}/create-content
POST /api/v1/content/{id}/generate-draft
POST /api/v1/content/{id}/run-qc
POST /api/v1/content/{id}/approve   (acts on the package's opportunity)
POST /api/v1/content/{id}/reject
POST /api/v1/content/{id}/export
GET  /api/v1/content/{id}           (package view)

All workspace-scoped; server-side authorization revalidated (Doc 08).
"""

import json
import tempfile
import zipfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from packages.domain.editorial import ContentPackage, Opportunity
from packages.domain.enums import ContentFormat
from packages.research.content import ContentService, PublicationBlocked
from packages.research.opportunity import OpportunityService
from packages.shared.db import get_session
from packages.shared.settings import get_settings

router = APIRouter(prefix="/api/v1")


class CreateContentBody(BaseModel):
    format: str
    editorial_angle: str | None = None
    key_message: str | None = None
    seo_entities: list[str] = Field(default_factory=list)
    cta_policy: dict | None = None


class DraftBody(BaseModel):
    title: str
    caption: str
    claim_ids_used: list[UUID] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)


class RejectBody(BaseModel):
    reason: str


class ExportBody(BaseModel):
    platform: str


def _package_scoped(session: Session, package_id: UUID, workspace_id: UUID) -> ContentPackage:
    package = session.get(ContentPackage, package_id)
    if package is None or package.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="content package not found")
    return package


def _opportunity_of(session: Session, package: ContentPackage) -> Opportunity:
    opp = session.get(Opportunity, package.opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return opp


@router.post("/opportunities/{opportunity_id}/create-content")
def create_content(
    opportunity_id: UUID,
    body: CreateContentBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    opps = OpportunityService(session)
    opp = opps.get_scoped(opportunity_id, workspace_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    try:
        format = ContentFormat(body.format)
    except ValueError as err:
        raise HTTPException(
            status_code=422, detail="format must be PHOTO_POST, CAROUSEL or MICROLOOP"
        ) from err
    content = ContentService(session)
    package = content.create_content(
        opps.get_session_ctx(opp),
        opp,
        format=format,
        editorial_angle=body.editorial_angle,
        key_message=body.key_message,
        seo_entities=body.seo_entities,
        cta_policy=body.cta_policy,
    )
    return {"package_id": str(package.id), "format": package.format, "opportunity_state": opp.state}


@router.post("/content/{package_id}/generate-draft")
def generate_draft(
    package_id: UUID,
    body: DraftBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    package = _package_scoped(session, package_id, workspace_id)
    opp = _opportunity_of(session, package)
    ctx = OpportunityService(session).get_session_ctx(opp)
    try:
        draft = ContentService(session).generate_draft(
            ctx,
            package,
            title=body.title,
            caption=body.caption,
            claim_ids_used=body.claim_ids_used,
            payload=body.payload,
        )
    except PublicationBlocked as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return {"draft_id": str(draft.id), "status": draft.status}


@router.post("/content/{package_id}/run-qc")
def run_qc(
    package_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    package = _package_scoped(session, package_id, workspace_id)
    opp = _opportunity_of(session, package)
    ctx = OpportunityService(session).get_session_ctx(opp)
    return ContentService(
        session,
        asset_root=Path(get_settings().asset_root),
    ).run_qc(ctx, package)


@router.post("/content/{package_id}/approve")
def approve(
    package_id: UUID,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    package = _package_scoped(session, package_id, workspace_id)
    opp = _opportunity_of(session, package)
    try:
        ContentService(session).approve(
            OpportunityService(session).get_session_ctx(opp), opp
        )
    except PublicationBlocked as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return {"opportunity_id": str(opp.id), "state": opp.state}


@router.post("/content/{package_id}/reject")
def reject(
    package_id: UUID,
    body: RejectBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    package = _package_scoped(session, package_id, workspace_id)
    opp = _opportunity_of(session, package)
    ContentService(session).reject(
        OpportunityService(session).get_session_ctx(opp), opp, reason=body.reason
    )
    return {"opportunity_id": str(opp.id), "state": opp.state}


@router.post("/content/{package_id}/export")
def export(
    package_id: UUID,
    body: ExportBody,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    package = _package_scoped(session, package_id, workspace_id)
    opp = _opportunity_of(session, package)
    settings = get_settings()
    content = ContentService(
        session,
        export_root=Path(settings.export_root),
        asset_root=Path(settings.asset_root),
    )
    try:
        export_dir = content.export_package(
            OpportunityService(session).get_session_ctx(opp), package, platform=body.platform
        )
    except PublicationBlocked as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return {"export_path": export_dir.name, "platform": body.platform}


@router.get("/content/{package_id}/export/download")
def download_export(
    package_id: UUID,
    background_tasks: BackgroundTasks,
    workspace_id: UUID = Query(...),
    session: Session = Depends(get_session),
):
    package = _package_scoped(session, package_id, workspace_id)
    opp = _opportunity_of(session, package)
    root = Path(get_settings().export_root).resolve()
    export_dirs = sorted(root.glob(f"post-*-{str(package.id)[:8]}"))
    export_dir = export_dirs[-1].resolve() if export_dirs else None
    if (
        export_dir is None
        or not export_dir.is_relative_to(root)
        or not export_dir.is_dir()
    ):
        raise HTTPException(status_code=404, detail="export package not found")
    manifest_path = export_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["package_id"] != str(package.id):
            raise ValueError("manifest does not match content package")
        platform = manifest["platform"]
        if not isinstance(platform, str) or not platform:
            raise ValueError("invalid export platform")
        ContentService(session, asset_root=Path(get_settings().asset_root)).publisher_gate(
            OpportunityService(session).get_session_ctx(opp), package, platform
        )
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="export package is invalid") from exc
    except PublicationBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    files: list[tuple[Path, str]] = []
    for candidate in export_dir.rglob("*"):
        if candidate.is_symlink():
            continue
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(export_dir):
            raise HTTPException(status_code=409, detail="export contains an invalid path")
        files.append((resolved, resolved.relative_to(export_dir).as_posix()))
    if not files:
        raise HTTPException(status_code=404, detail="export package is empty")

    temp_root = Path(get_settings().temp_root).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    archive_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="urdia-export-",
            suffix=".zip",
            dir=temp_root,
            delete=False,
        ) as archive:
            archive_path = Path(archive.name)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path, arcname in files:
                archive.write(file_path, arcname)
    except OSError:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(archive_path.unlink, missing_ok=True)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"urdia-export-{opp.id}.zip",
        background=background_tasks,
    )
