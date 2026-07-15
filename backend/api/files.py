"""
backend/api/files.py

File upload and download endpoints.

  POST /api/upload          — Upload a file without starting analysis.
                              Returns file_id and stored_filename only.
                              Used when the client wants to stage a file
                              before committing to a full analysis run.

  GET  /api/download/{filename}
                            — Stream any processed file (clean CSV,
                              engineered CSV, raw upload) back to the
                              browser.  Only filenames that exist on
                              disk inside the configured upload or
                              processed directories are served — no path
                              traversal is permitted.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from backend.config import get_settings
from backend.db.models import Session as SessionModel
from backend.db.session import DbSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["files"])

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx", ".xls"})


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Returned after a bare file upload (no analysis started)."""

    file_id: str
    stored_filename: str
    original_filename: str
    size_bytes: int


# ---------------------------------------------------------------------------
# POST /api/upload
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Stage a file for later analysis (no pipeline started)",
)
async def upload_file(file: UploadFile) -> UploadResponse:
    """
    Upload a CSV or Excel file without triggering the Phase 1 pipeline.

    Use POST /api/analyze/start when you want to upload and immediately
    start analysis.  This endpoint is for clients that stage a file first
    and start analysis later (e.g. after the user confirms settings).
    """
    settings = get_settings()

    fname = file.filename or "upload"
    ext = Path(fname).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {len(content):,} B exceeds "
                f"the {settings.max_upload_size_mb} MB limit"
            ),
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / stored_name
    dest.write_bytes(content)

    # No DB row created here — the File record is created with a session_id
    # when POST /api/analyze/start is called.  This endpoint only stages the
    # file on disk and returns a reference the client can pass to start.
    staged_id = uuid.uuid4().hex
    logger.info("File staged — id=%s name=%s size=%d B", staged_id, fname, len(content))
    return UploadResponse(
        file_id=staged_id,
        stored_filename=stored_name,
        original_filename=fname,
        size_bytes=len(content),
    )


# ---------------------------------------------------------------------------
# GET /api/download/{filename}
# ---------------------------------------------------------------------------


@router.get(
    "/download/{filename}",
    summary="Download a processed file by stored filename",
)
async def download_file(filename: str, db: DbSession) -> FileResponse:
    """
    Stream a stored file back to the browser.

    ``filename`` must be the bare stored filename (e.g.
    ``abc123_clean.csv``) — not a full path.  The server resolves the
    file relative to the configured upload and processed directories.
    Path traversal sequences (``..``) are rejected with 400.

    The Content-Disposition filename sent to the browser is upgraded to
    a human-readable name derived from the session's original upload
    (e.g. ``orders_2024_q4_clean.csv``) when the owning session can be
    found. This is display-only — the on-disk path/lookup logic above
    is unchanged, and it falls back to the bare stored filename if no
    matching session exists.
    """
    settings = get_settings()

    # Reject any path traversal attempt
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename — path separators are not permitted.",
        )

    # Search upload dir then processed dir
    candidate_dirs: list[Path] = [settings.upload_dir, settings.processed_dir]
    resolved: Path | None = None
    for directory in candidate_dirs:
        candidate = directory / filename
        if candidate.is_file():
            resolved = candidate
            break

    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{filename}' not found.",
        )

    media_type, _ = mimetypes.guess_type(filename)
    if media_type is None:
        media_type = "application/octet-stream"

    # Upgrade the download filename to a human-readable one, display-only.
    # Falls back to the bare stored `filename` on any lookup miss.
    display_name = filename
    session_row: SessionModel | None = None
    for suffix in ("_clean.csv", "_engineered.csv"):
        if filename.endswith(suffix):
            candidate_id = filename[: -len(suffix)]
            try:
                session_row = await db.get(SessionModel, uuid.UUID(candidate_id))
            except ValueError:
                session_row = None
            if session_row is not None:
                base = Path(session_row.original_filename).stem
                display_name = f"{base}{suffix}"
            break
    else:
        result = await db.execute(
            select(SessionModel).where(SessionModel.stored_filename == filename)
        )
        session_row = result.scalar_one_or_none()
        if session_row is not None:
            display_name = session_row.original_filename

    return FileResponse(
        path=str(resolved),
        filename=display_name,
        media_type=media_type,
    )
