"""/api/v1/imports: upload the legacy lead workbook and read the per-row result (FR-02).

Mounted on the protected router in app.main, so every route requires a signed-in staff member.
"""

from __future__ import annotations

import logging
from pathlib import PurePath
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.auth.router import CurrentStaff
from app.db import Db, engine
from app.errors import ApiError
from app.imports.decisions import Decision, decide
from app.imports.models import ImportAccepted, ImportDecisionRequest, ImportResult
from app.imports.results import load_result
from app.imports.service import file_hash, record_failed_upload, stage_upload, write_import
from app.imports.workbook import MAX_UPLOAD_BYTES, WorkbookError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])

# Room for multipart boundaries and part headers on top of the workbook itself.
_MULTIPART_ALLOWANCE = 64 * 1024

# The body is parsed by hand (see upload_workbook), so describe it for the OpenAPI schema.
_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary", "description": "Legacy .xlsx workbook"}},
                }
            }
        },
    }
}


@router.post("", status_code=202, openapi_extra=_UPLOAD_BODY)
async def upload_workbook(request: Request, user: CurrentStaff) -> ImportAccepted:
    """Import the workbook and return its batch; GET /imports/{batch_id} has the row results.

    The multipart body is read here rather than through an UploadFile parameter: FastAPI reads declared
    body parameters before running dependencies, so a client without a session could make the server
    spool a large file before getting its 401. Here require_staff has already passed.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + _MULTIPART_ALLOWANCE:
        raise ApiError(413, "workbook_too_large", "Workbook is larger than 10 MiB")
    async with request.form(max_files=1, max_fields=1) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise ApiError(422, "validation_error", "Request validation failed", [{"field": "file", "message": "Field required"}])
        # Browsers send a bare name, other clients may send a path; keep only the name, bounded.
        filename = PurePath((upload.filename or "").replace("\\", "/")).name[:255]
        if not filename.lower().endswith(".xlsx"):
            raise ApiError(422, "unsupported_file_type", "Upload the lead workbook as an .xlsx file")
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
    # Parsing and the database work are blocking; keep them off the event loop.
    return await run_in_threadpool(_import, data, filename, user.user_id)


def _import(data: bytes, filename: str, user_id: UUID) -> ImportAccepted:
    try:
        staged = stage_upload(data)
    except WorkbookError as error:
        # A file that cannot be read as the legacy format writes nothing.
        raise ApiError(error.status_code, error.code, error.message, error.details) from error
    sha = file_hash(data)
    try:
        with engine.begin() as conn:
            outcome = write_import(conn, staged, sha, filename, user_id)
    except Exception:
        # The import transaction rolled back. Leave a failed batch so staff can see the attempt, then let
        # the error middleware answer 500. Uploading again is the retry path.
        try:
            with engine.begin() as conn:
                record_failed_upload(conn, sha, filename, user_id)
        except Exception:
            # Typically the same outage; never let it replace the original error.
            logger.warning("Could not record the failed import batch")
        raise
    # Batch ID and state only: never file names' or rows' contents in logs.
    logger.info("Import batch %s: %s%s", outcome.batch_id, outcome.state, " (replayed)" if outcome.replayed else "")
    return ImportAccepted(batch_id=outcome.batch_id, state=outcome.state, replayed=outcome.replayed)


@router.get("/{batch_id}")
def get_import(batch_id: UUID, conn: Db) -> ImportResult:
    result = load_result(conn, batch_id)
    if result is None:
        raise ApiError(404, "not_found", "Import batch not found")
    return result


@router.post("/{batch_id}/decisions")
def decide_rows(batch_id: UUID, body: ImportDecisionRequest, user: CurrentStaff, conn: Db) -> ImportResult:
    """Resolve needs_review rows: create one clinic from them, link them to a clinic, or reject them.

    Returns the updated batch. 409 row_already_decided when another staff member decided a row first.
    """
    decide(
        conn,
        batch_id,
        Decision(
            import_row_ids=body.import_row_ids,
            action=body.action,
            reason=body.reason,
            clinic_id=body.clinic_id,
            clinic_name=body.clinic_name,
        ),
        user.user_id,
    )
    return load_result(conn, batch_id)
