"""Case import endpoints (CSV / XLSX, up to 1000 rows, synchronous)."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.deps import DbSession, require_roles
from app.errors import ApiError
from app.models.system import ImportJob
from app.models.users import User
from app.schemas.reporting import ImportJobOut, ImportPreview, ImportRowError
from app.services import importer

router = APIRouter(prefix="/imports", tags=["imports"])
Importer = Annotated[User, Depends(require_roles(*importer.IMPORT_ROLES))]


def _job_out(job: ImportJob) -> ImportJobOut:
    errs = [ImportRowError(row=int(e.get("row", 0)), message=str(e.get("message", ""))) for e in job.errors or []]
    return ImportJobOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        mapping=dict(job.mapping or {}),
        total_rows=job.total_rows,
        imported=job.imported,
        auto_suggested=job.auto_suggested,
        needs_review=job.needs_review,
        unresolved=job.unresolved,
        links_found=job.links_found,
        error_count=len(errs),
        errors=errs,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get("/template.csv")
def template(_user: Importer) -> Response:
    return Response(
        importer.template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="lok_sutra_import_template.csv"'},
    )


@router.post("/preview", response_model=ImportPreview)
async def preview(_user: Importer, file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read(importer.MAX_BYTES + 1)
    return importer.preview(file.filename or "upload", content)


@router.post("", response_model=ImportJobOut)
async def create_import(
    db: DbSession, user: Importer, file: UploadFile = File(...), mapping: str = Form(...)
) -> ImportJobOut:
    try:
        mapping_obj = json.loads(mapping)
    except ValueError:
        raise ApiError(422, "INVALID_MAPPING", "mapping must be valid JSON") from None
    content = await file.read(importer.MAX_BYTES + 1)
    job = importer.run_import(db, user, file.filename or "upload", content, mapping_obj)
    return _job_out(job)


@router.get("/{job_id}", response_model=ImportJobOut)
def get_import(job_id: uuid.UUID, db: DbSession, _user: Importer) -> ImportJobOut:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Import job not found")
    return _job_out(job)


@router.get("/{job_id}/errors.csv")
def get_import_errors(job_id: uuid.UUID, db: DbSession, _user: Importer) -> Response:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Import job not found")
    return Response(
        importer.errors_csv(job),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import_{job_id}_errors.csv"'},
    )
