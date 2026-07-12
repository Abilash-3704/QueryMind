"""POST /upload — accept one or more CSV files, load into a session DuckDB connection."""
from __future__ import annotations

import duckdb
from app.config import Settings, get_settings
from app.db.session_db import append_csv_to_session, load_csv_to_session
from app.models.schemas import UploadResponse
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    """Upload one or more CSV files.

    All files are loaded into a single new session (one table per file, named after
    the filename stem). Returns a session_id to use in subsequent /query calls.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    ttl = settings.session_ttl_minutes * 60

    first = files[0]
    first_bytes = await first.read()
    try:
        session = load_csv_to_session(
            csv_bytes=first_bytes,
            filename=first.filename or "upload.csv",
            ttl_seconds=ttl,
        )
    except duckdb.Error as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse '{first.filename}': {exc}",
        ) from exc

    for extra in files[1:]:
        extra_bytes = await extra.read()
        try:
            append_csv_to_session(session, extra_bytes, extra.filename or "extra.csv")
        except duckdb.Error as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Could not parse '{extra.filename}': {exc}",
            ) from exc

    table_count = len(session.schema_info.tables)
    return UploadResponse(
        session_id=session.session_id,
        tables=session.schema_info.tables,
        expires_in_minutes=settings.session_ttl_minutes,
        message=f"Loaded {table_count} table{'s' if table_count != 1 else ''}.",
    )
