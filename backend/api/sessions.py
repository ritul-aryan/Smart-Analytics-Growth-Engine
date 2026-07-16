"""
backend/api/sessions.py

Session read endpoints — polled by the frontend after every pipeline phase.

  GET /api/sessions              — list all sessions (home page)
  GET /api/session/{session_id}  — full session detail with anomalies,
                                   audit log, charts, and EDA narrative
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from backend.db.models import Anomaly, AuditLog, Chart, Session
from backend.db.session import DbSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])


# ---------------------------------------------------------------------------
# NaN / Inf sanitisation — prevents browser JSON.parse failures
# ---------------------------------------------------------------------------

def _sanitize_nan(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None for valid JSON output."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Response schemas  (mirror frontend/src/types/session.ts + chart.ts)
# ---------------------------------------------------------------------------

class SessionOut(BaseModel):
    id: str
    created_at: str
    updated_at: str
    status: str
    original_filename: str
    stored_filename: str
    user_intent: str | None
    llm_provider: str | None
    row_count: int | None
    col_count: int | None
    quality_score_before: float | None
    quality_score_after: float | None
    column_renames: dict[str, str] | None
    metadata_summary: str | None
    error_message: str | None
    warnings: list[str] | None = None
    parent_session_id: str | None = None


class AnomalyOut(BaseModel):
    id: str
    session_id: str
    anomaly_type: str
    column_name: str | None
    affected_rows: int
    null_rate: float | None
    severity: str
    details: dict[str, Any]
    user_action: str | None
    action_params: dict[str, Any] | None
    resolved_at: str | None
    display_order: int


class AuditLogOut(BaseModel):
    id: str
    session_id: str
    agent_name: str
    phase: str
    action: str
    reason: str
    column_affected: str | None
    rows_affected: int
    before_value: dict[str, Any] | None
    after_value: dict[str, Any] | None
    is_llm_decision: bool
    llm_prompt_summary: str | None
    timestamp: str


class ChartOut(BaseModel):
    id: str
    session_id: str
    chart_type: str
    title: str
    plotly_config: dict[str, Any]
    insight_text: str | None
    columns_used: list[str]
    display_order: int
    created_at: str


class SessionDetailResponse(BaseModel):
    session: SessionOut
    anomalies: list[AnomalyOut]
    audit_log: list[AuditLogOut]
    charts: list[ChartOut]
    eda_narrative: dict[str, Any] | None


class SessionListResponse(BaseModel):
    sessions: list[SessionOut]
    total: int


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------

@router.get(
    "/api/sessions",
    response_model=SessionListResponse,
    summary="List all sessions, newest first",
)
async def list_sessions(db: DbSession) -> SessionListResponse:
    rows = (
        await db.execute(select(Session).order_by(Session.created_at.desc()))
    ).scalars().all()
    return SessionListResponse(
        sessions=[_session_out(s) for s in rows],
        total=len(rows),
    )


# ---------------------------------------------------------------------------
# GET /api/session/{session_id}
# ---------------------------------------------------------------------------

@router.get(
    "/api/session/{session_id}",
    response_model=SessionDetailResponse,
    summary="Full session detail — polled by UploadPage and AuditPage",
)
async def get_session(session_id: str, db: DbSession) -> SessionDetailResponse:
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_row = await db.get(Session, sid)
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    anomalies = (
        await db.execute(
            select(Anomaly)
            .where(Anomaly.session_id == sid)
            .order_by(Anomaly.display_order)
        )
    ).scalars().all()

    audit_entries = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.session_id == sid)
            .order_by(AuditLog.timestamp)
        )
    ).scalars().all()

    charts = (
        await db.execute(
            select(Chart)
            .where(Chart.session_id == sid)
            .order_by(Chart.display_order)
        )
    ).scalars().all()

    narrative: dict[str, Any] | None = None
    if session_row.narrative:  # type: ignore[attr-defined]
        try:
            raw = json.loads(session_row.narrative)  # type: ignore[attr-defined]
            narrative = _sanitize_nan(raw)  # strip NaN/Inf so browser JSON.parse succeeds
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse narrative JSON for session %s", session_id)

    return SessionDetailResponse(
        session=_session_out(session_row),
        anomalies=[_anomaly_out(a) for a in anomalies],
        audit_log=[_audit_out(e) for e in audit_entries],
        charts=[_chart_out(c) for c in charts],
        eda_narrative=narrative,
    )


# DELETE /api/sessions/{session_id}

@router.delete(
    "/api/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session and all its associated data",
)
async def delete_session(session_id: str, db: DbSession) -> None:
    """
    Hard-delete a session.  SQLAlchemy cascade removes all child rows:
    anomalies, audit_log, charts, files, chat_messages.
    Returns 204 No Content on success.
    """
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_row = await db.get(Session, sid)
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session_row)
    await db.commit()
    logger.info("Session %s deleted with all child rows", session_id)


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _session_out(s: Session) -> SessionOut:
    return SessionOut(
        id=str(s.id),
        created_at=s.created_at.isoformat(),  # type: ignore[attr-defined]
        updated_at=s.updated_at.isoformat(),  # type: ignore[attr-defined]
        status=s.status.value,  # type: ignore[attr-defined]
        original_filename=s.original_filename,  # type: ignore[attr-defined]
        stored_filename=s.stored_filename,  # type: ignore[attr-defined]
        user_intent=s.user_intent,  # type: ignore[attr-defined]
        llm_provider=s.llm_provider,  # type: ignore[attr-defined]
        row_count=s.row_count,  # type: ignore[attr-defined]
        col_count=s.col_count,  # type: ignore[attr-defined]
        quality_score_before=s.quality_score_before,  # type: ignore[attr-defined]
        quality_score_after=s.quality_score_after,  # type: ignore[attr-defined]
        column_renames=s.column_renames,  # type: ignore[attr-defined]
        metadata_summary=s.metadata_summary,  # type: ignore[attr-defined]
        error_message=s.error_message,  # type: ignore[attr-defined]
        warnings=s.warnings,  # type: ignore[attr-defined]
        parent_session_id=str(s.parent_session_id) if s.parent_session_id else None,  # type: ignore[attr-defined]
    )


def _anomaly_out(a: Anomaly) -> AnomalyOut:
    return AnomalyOut(
        id=str(a.id),
        session_id=str(a.session_id),
        anomaly_type=a.anomaly_type.value,  # type: ignore[attr-defined]
        column_name=a.column_name,  # type: ignore[attr-defined]
        affected_rows=a.affected_rows,  # type: ignore[attr-defined]
        null_rate=a.null_rate,  # type: ignore[attr-defined]
        severity=a.severity.value,  # type: ignore[attr-defined]
        details=a.details or {},  # type: ignore[attr-defined]
        user_action=a.user_action,  # type: ignore[attr-defined]
        action_params=a.action_params,  # type: ignore[attr-defined]
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,  # type: ignore[attr-defined]
        display_order=a.display_order,  # type: ignore[attr-defined]
    )


def _audit_out(e: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=str(e.id),
        session_id=str(e.session_id),
        agent_name=e.agent_name,  # type: ignore[attr-defined]
        phase=e.phase,  # type: ignore[attr-defined]
        action=e.action,  # type: ignore[attr-defined]
        reason=e.reason,  # type: ignore[attr-defined]
        column_affected=e.column_affected,  # type: ignore[attr-defined]
        rows_affected=e.rows_affected,  # type: ignore[attr-defined]
        before_value=e.before_value,  # type: ignore[attr-defined]
        after_value=e.after_value,  # type: ignore[attr-defined]
        is_llm_decision=e.is_llm_decision or False,  # type: ignore[attr-defined]
        llm_prompt_summary=e.llm_prompt_summary,  # type: ignore[attr-defined]
        timestamp=e.timestamp.isoformat(),
    )


def _chart_out(c: Chart) -> ChartOut:
    raw_cfg = c.plotly_config if isinstance(c.plotly_config, dict) else {}  # type: ignore[attr-defined]
    cfg = _sanitize_nan(raw_cfg)  # strip NaN/Inf so browser JSON.parse succeeds
    return ChartOut(
        id=str(c.id),
        session_id=str(c.session_id),
        chart_type=c.chart_type,  # type: ignore[attr-defined]
        title=c.title or "",  # type: ignore[attr-defined]
        plotly_config=cfg,
        insight_text=c.insight_text or None,  # type: ignore[attr-defined]
        columns_used=c.columns_used or [],  # type: ignore[attr-defined]
        display_order=c.display_order or 0,  # type: ignore[attr-defined]
        created_at=c.created_at.isoformat(),  # type: ignore[attr-defined]
    )
