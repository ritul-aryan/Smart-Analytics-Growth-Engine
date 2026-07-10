"""
tests/test_api.py

Integration tests for FastAPI endpoints.
Uses httpx.AsyncClient with the FastAPI app wired to an in-memory SQLite DB.

Covers:
  GET  /health
  POST /api/analyze/start  — 202 + session_id
  GET  /api/session/{id}   — 200 with session detail / 404 for unknown
  GET  /api/sessions        — 200 list
  POST /api/analyze/complete — 202 / 409 for wrong status
"""

from __future__ import annotations

import io
import uuid

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Session, SessionStatus


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def test_health(async_client: AsyncClient) -> None:
    # Mounted at bare /health, not /api/health -- per Section 4.2/9.1 of
    # MAE_Master_Architecture_v2.docx (2026-07-03 architecture audit,
    # decision log item 4). See backend/api/health.py for the full history.
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/analyze/start
# ---------------------------------------------------------------------------

async def test_analyze_start_returns_202(async_client: AsyncClient) -> None:
    csv_bytes = b"id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,40\n"
    resp = await async_client.post(
        "/api/analyze/start",
        files={"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"user_intent": "explore age distribution"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "session_id" in body
    assert body["status"] == "upload"


async def test_analyze_start_rejects_invalid_type(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/api/analyze/start",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"user_intent": "test"},
    )
    assert resp.status_code == 422


async def test_analyze_start_rejects_oversized_file(async_client: AsyncClient) -> None:
    from backend.config import get_settings
    settings = get_settings()
    big = b"a,b\n" + b"1,2\n" * 1_000
    # Patch max size to 1 byte to force rejection
    original = settings.max_upload_size_mb
    try:
        object.__setattr__(settings, "max_upload_size_mb", 0)
        object.__setattr__(settings, "_max_upload_size_bytes", 1)
        resp = await async_client.post(
            "/api/analyze/start",
            files={"file": ("big.csv", io.BytesIO(big), "text/csv")},
            data={"user_intent": "test"},
        )
        assert resp.status_code == 413
    finally:
        object.__setattr__(settings, "max_upload_size_mb", original)
        object.__setattr__(settings, "_max_upload_size_bytes", original * 1024 * 1024)


# ---------------------------------------------------------------------------
# GET /api/session/{id}
# ---------------------------------------------------------------------------

async def test_get_session_not_found(async_client: AsyncClient) -> None:
    resp = await async_client.get(f"/api/session/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_session_invalid_id(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/session/not-a-uuid")
    assert resp.status_code == 400


async def test_get_session_returns_detail(
    async_client: AsyncClient, db: AsyncSession,
) -> None:
    sid = uuid.uuid4()
    db.add(Session(
        id=sid,
        original_filename="sample.csv",
        stored_filename="sample.csv",
        status=SessionStatus.AUDIT,
    ))
    await db.flush()

    resp = await async_client.get(f"/api/session/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["id"] == str(sid)
    assert body["session"]["status"] == "audit"
    assert isinstance(body["anomalies"], list)
    assert isinstance(body["charts"], list)
    assert isinstance(body["audit_log"], list)


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------

async def test_list_sessions_empty(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body
    assert "total" in body


async def test_list_sessions_returns_created(
    async_client: AsyncClient, db: AsyncSession,
) -> None:
    for i in range(3):
        db.add(Session(
            id=uuid.uuid4(),
            original_filename=f"file{i}.csv",
            stored_filename=f"file{i}.csv",
            status=SessionStatus.UPLOAD,
        ))
    await db.flush()

    resp = await async_client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 3


# ---------------------------------------------------------------------------
# POST /api/analyze/complete
# ---------------------------------------------------------------------------

async def test_complete_wrong_status_returns_409(
    async_client: AsyncClient, db: AsyncSession,
) -> None:
    sid = uuid.uuid4()
    db.add(Session(
        id=sid,
        original_filename="f.csv",
        stored_filename="f.csv",
        status=SessionStatus.UPLOAD,  # NOT audit
    ))
    await db.flush()

    resp = await async_client.post(
        "/api/analyze/complete",
        json={"session_id": str(sid), "decisions": []},
    )
    assert resp.status_code == 409


async def test_complete_unknown_session_returns_404(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/api/analyze/complete",
        json={"session_id": str(uuid.uuid4()), "decisions": []},
    )
    assert resp.status_code == 404


async def test_complete_returns_202_for_audit_session(
    async_client: AsyncClient, db: AsyncSession,
) -> None:
    sid = uuid.uuid4()
    db.add(Session(
        id=sid,
        original_filename="f.csv",
        stored_filename="f.csv",
        status=SessionStatus.AUDIT,
    ))
    await db.flush()

    resp = await async_client.post(
        "/api/analyze/complete",
        json={"session_id": str(sid), "decisions": []},
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "processing"
