"""
backend/api/analyze.py

Phase 1, 2, and 3 endpoints -- both live in this one file per Section 4.2 of
MAE_Master_Architecture_v2.docx, which assigns POST /api/analyze/start AND
POST /api/analyze/complete to analyze.py (not a separate complete.py).

  POST /api/analyze/start    -- Upload a file, run Phase 1 (Orchestrator/Profiler).
  POST /api/analyze/complete -- Submit HITL decisions, run Phase 2+3
                                (Janitor -> Engineer -> Storyteller).

Frontend polls GET /api/session/{id} for status updates:
  upload    -> audit     (Phase 1 complete -- anomalies ready for HITL review)
  audit     -> processing -> complete (after Phase 2+3)

History: this file and backend/api/complete.py were split apart during
earlier development (each individually still exceeded the project's old
150-line-per-route-file cap). The 2026-07-03 architecture audit flagged the
split as a spec deviation (decision log item 2). Since the line-limit policy
was lifted the same day, the two are merged back together here to match the
spec exactly; the old complete.py has been moved to junk-unused-dump/.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.storyteller import sanitize_json
from ai_engine.config import CSV_ENCODING_FALLBACKS
from ai_engine.graph.state import AnomalyRecord, ChartSpec
from ai_engine.graph.workflow import build_phase1_app, build_phase2_app
from ai_engine.llm.factory import get_llm_provider
from backend.config import LLM_API_KEY_HEADER, get_settings
from backend.db.models import (
    Anomaly, AnomalyType, Chart, File, FileType, Session, SessionStatus, Severity,
)
from backend.db.session import AsyncSessionLocal, DbSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["analyze"])

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx", ".xls"})


# ---------------------------------------------------------------------------
# Response / request schemas
# ---------------------------------------------------------------------------


class AnalyzeStartResponse(BaseModel):
    """Returned immediately after upload; contains session_id for polling."""

    session_id: str
    status: str
    message: str


class DecisionItem(BaseModel):
    anomaly_id: str
    action: str
    params: dict[str, Any] | None = None


class AnalyzeCompleteRequest(BaseModel):
    session_id: str
    decisions: list[DecisionItem]


class AnalyzeCompleteResponse(BaseModel):
    session_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# POST /api/analyze/start
# ---------------------------------------------------------------------------


@router.post(
    "/start",
    response_model=AnalyzeStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a file and start Phase 1 anomaly detection",
)
async def analyze_start(
    background_tasks: BackgroundTasks,
    db: DbSession,
    file: UploadFile,
    user_intent:            Annotated[str,   Form()] = "",
    llm_provider:           Annotated[str,   Form()] = "",
    ohe_max_unique:         Annotated[int,   Form()] = 10,
    log_skew_threshold:     Annotated[float, Form()] = 1.5,
    correlation_threshold:  Annotated[float, Form()] = 0.50,
    outlier_iqr_multiplier: Annotated[float, Form()] = 3.0,
    null_density_threshold: Annotated[float, Form()] = 0.50,
    # BYOK: optional user-supplied LLM API key. Overrides the .env key for
    # this request only. Never persisted, never logged.
    api_key: Annotated[str | None, Header(alias=LLM_API_KEY_HEADER)] = None,
) -> AnalyzeStartResponse:
    """
    Accept a CSV or Excel file and fire the Phase 1 pipeline in the background.

    Returns 202 immediately. Poll GET /api/session/{id} until status is 'audit'
    to confirm Phase 1 has completed and anomaly cards are ready.

    Key ordering guarantee
    ----------------------
    We call ``await db.commit()`` explicitly BEFORE adding the background task.
    Starlette runs BackgroundTasks as part of ``response.__call__()``, while the
    ``get_db`` yield-dependency cleanup (which also commits) runs AFTER that.
    Without the explicit commit the background task's fresh AsyncSession cannot
    see the Session or File rows on PostgreSQL (read-committed isolation) and
    Phase 1 fails silently, leaving the session perpetually in "upload" status.
    """
    settings = get_settings()

    # --- Validate file extension ---
    fname = file.filename or "upload"
    ext = Path(fname).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    # --- Read and validate file size ---
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {len(content):,} B exceeds the {settings.max_upload_size_mb} MB limit"
            ),
        )

    # --- Persist file to disk (off the event loop to avoid blocking) ---
    stored_name = f"{uuid.uuid4().hex}{ext}"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / stored_name
    await asyncio.to_thread(dest.write_bytes, content)

    # --- Resolve LLM provider (form field overrides .env default) ---
    provider = llm_provider.strip() or settings.llm_provider

    # --- Create Session row ---
    session_row = Session(
        original_filename=fname,
        stored_filename=stored_name,
        status=SessionStatus.UPLOAD,
        user_intent=user_intent.strip() or None,
        llm_provider=provider,
    )
    db.add(session_row)
    await db.flush()
    session_id = str(session_row.id)

    # --- Create File record (RAW version) ---
    db.add(File(
        session_id=session_row.id,
        file_type=FileType.RAW,
        storage_path=str(dest),
        original_name=fname,
        size_bytes=len(content),
    ))
    await db.flush()

    # --- Commit NOW so the background task can see the rows on all DB backends ---
    # Without this explicit commit the background task (running before get_db
    # cleanup) cannot find the Session or File rows on PostgreSQL.
    await db.commit()

    # --- Queue background task (Phase 1 runs after 202 is sent to client) ---
    background_tasks.add_task(
        _run_phase1_background,
        session_id=session_id,
        file_path=str(dest),
        user_intent=user_intent.strip() or "",
        llm_provider=provider,
        api_key=api_key,
        pipeline_settings={
            "ohe_max_unique":         ohe_max_unique,
            "log_skew_threshold":     log_skew_threshold,
            "correlation_threshold":  correlation_threshold,
            "outlier_iqr_multiplier": outlier_iqr_multiplier,
            "null_density_threshold": null_density_threshold,
        },
    )

    logger.info(
        "Phase 1 queued -- session=%s file=%s provider=%s size=%d B",
        session_id, fname, provider, len(content),
    )
    return AnalyzeStartResponse(
        session_id=session_id,
        status=SessionStatus.UPLOAD.value,
        message="Phase 1 pipeline started. Poll GET /api/session/{id} for status.",
    )


# ---------------------------------------------------------------------------
# Background task -- Phase 1
# ---------------------------------------------------------------------------


async def _run_phase1_background(
    session_id: str,
    file_path: str,
    user_intent: str,
    llm_provider: str,
    api_key: str | None = None,
    pipeline_settings: dict[str, Any] | None = None,
) -> None:
    """
    Run Phase 1 pipeline in a fresh database session.

    The request-scoped session was explicitly committed before this task was
    queued, so the Session and File rows are guaranteed to be visible here on
    both SQLite (StaticPool) and PostgreSQL.

    api_key -- optional BYOK key from the request header. Passed to the LLM
    factory for this run only; never written to the database or logs.

    pipeline_settings -- user-configurable thresholds from the UI (Section 8.3).
    They are injected into GraphState and override ai_engine/config.py defaults.

    Execution runs through ai_engine/graph/workflow.py's phase1_app (a
    compiled LangGraph app) rather than calling run_phase1() directly.
    build_phase1_app() is a factory: it compiles a fresh graph per call whose
    single "orchestrator" node closes over this run's llm/auditor, since
    those are per-request resources that cannot live in GraphState. It takes
    no db parameter -- ai_engine never touches the database directly
    (2026-07-03 architecture audit, decision log item 7); this function
    persists the pipeline's results using its own `db` session below. See
    the module docstring in ai_engine/graph/workflow.py for why phase1_app
    has one node instead of separate orchestrator/profiler nodes.
    """
    async with AsyncSessionLocal() as db:
        try:
            settings = get_settings()
            auditor = Auditor(db=db, session_id=session_id)
            llm = get_llm_provider(
                llm_provider,
                api_key=api_key,
                default_provider=settings.llm_provider,
                ollama_base_url=settings.ollama_base_url,
                gemini_api_key=settings.gemini_api_key,
            )

            state: dict[str, Any] = {
                "session_id": session_id,
                "llm_provider": llm_provider,
                "file_path": file_path,
                "user_intent": user_intent,
                **(pipeline_settings or {}),
            }

            # --- Ingestion validation: fail fast with a clear reason ---------------
            validation_error: str | None = None
            try:
                _df_check = _read_dataframe(file_path)
                if _df_check.shape[1] == 0:
                    validation_error = "The file has no columns to analyse."
                elif len(_df_check) == 0:
                    validation_error = (
                        "The file contains column headers but no data rows, so there is "
                        "nothing to analyse."
                    )
            except pd.errors.EmptyDataError:
                validation_error = "The file is empty."
            except pd.errors.ParserError as exc:
                validation_error = (
                    "The file could not be parsed as a valid CSV (rows have an "
                    f"inconsistent number of columns). Details: {exc}"
                )
            except Exception as exc:  # unknown read failure
                validation_error = f"The file could not be read: {exc}"
            if validation_error is not None:
                session_row = await db.get(Session, uuid.UUID(session_id))
                if session_row is not None:
                    session_row.status = SessionStatus.ERROR
                    session_row.error_message = validation_error[:500]
                    await db.flush()
                await db.commit()
                logger.warning(
                    "Phase 1 ingestion rejected session=%s: %s", session_id, validation_error
                )
                return
            # -----------------------------------------------------------------------

            phase1_app = build_phase1_app(llm=llm, auditor=auditor)
            result = await phase1_app.ainvoke(state)

            if "error" in result:
                logger.error("Phase 1 error session=%s: %s", session_id, result["error"])
                await db.commit()
                return

            # Persist anomaly_report to the anomalies table for the HITL audit
            # page. This used to happen inside orchestrator.run_phase1() itself;
            # it now happens here so ai_engine never imports backend.db.models
            # (2026-07-03 architecture audit, decision log item 7).
            await _persist_anomalies(db, session_id, result.get("anomaly_report", []))

            # Patch the sessions row with outputs the orchestrator does not write directly
            session_row = await db.get(Session, uuid.UUID(session_id))
            if session_row is not None:
                df = result.get("df_working")
                session_row.column_renames = result.get("column_renames")
                session_row.metadata_summary = result.get("metadata_summary")
                session_row.warnings = result.get("warnings") or None
                if df is not None:
                    session_row.row_count = len(df)
                    session_row.col_count = len(df.columns)
                await db.flush()

            await db.commit()
            logger.info(
                "Phase 1 done -- session=%s anomalies=%d score=%.1f",
                session_id,
                len(result.get("anomaly_report", [])),
                result.get("quality_score_before", 0.0),
            )

        except Exception as exc:
            logger.error(
                "Unhandled error in Phase 1 background task session=%s: %s",
                session_id, exc, exc_info=True,
            )
            await db.rollback()
            try:
                async with AsyncSessionLocal() as err_db:
                    err_row = await err_db.get(Session, uuid.UUID(session_id))
                    if err_row is not None:
                        err_row.status = SessionStatus.ERROR
                        err_row.error_message = f"Analysis failed: {exc}"[:500]
                        await err_db.commit()
            except Exception as inner:
                logger.error("Failed to record ERROR status session=%s: %s", session_id, inner)


# ---------------------------------------------------------------------------
# Helpers -- Phase 1
# ---------------------------------------------------------------------------

async def _persist_anomalies(
    db: AsyncSession,
    session_id: str,
    anomaly_report: list[dict[str, Any]],
) -> None:
    """
    Write anomaly records to the database for the HITL audit page.

    Moved here from ai_engine/agents/orchestrator.py so that ai_engine never
    imports backend.db.models directly (2026-07-03 architecture audit,
    decision log item 7). Does not commit -- the caller's transaction
    boundary controls when the commit happens.
    """
    sid = uuid.UUID(session_id)
    for rec in anomaly_report:
        db.add(Anomaly(
            session_id=sid,
            anomaly_type=AnomalyType(rec["anomaly_type"]),
            column_name=rec.get("column_name"),
            affected_rows=rec["affected_rows"],
            null_rate=rec.get("null_rate"),
            severity=Severity(rec["severity"]),
            details=rec.get("details", {}),
            display_order=rec["display_order"],
        ))
    await db.flush()


# ---------------------------------------------------------------------------
# POST /api/analyze/complete
# ---------------------------------------------------------------------------


@router.post(
    "/complete",
    response_model=AnalyzeCompleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit HITL decisions and start Phase 2+3 pipeline",
)
async def analyze_complete(
    body: AnalyzeCompleteRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> AnalyzeCompleteResponse:
    """
    Accept HITL decisions and fire Phase 2 (Janitor -> Engineer) + Phase 3
    (Storyteller) in a background task.  Returns 202 immediately.
    Poll GET /api/session/{id} until status is 'complete'.
    """
    try:
        session_id_uuid = uuid.UUID(body.session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_row = await db.get(Session, session_id_uuid)
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session_row.status not in (SessionStatus.AUDIT,):
        raise HTTPException(
            status_code=409,
            detail=f"Session is in status '{session_row.status.value}'; expected 'audit'",
        )

    now = datetime.now(tz=timezone.utc)
    decisions_raw = [d.model_dump() for d in body.decisions]

    # Persist decisions to anomaly rows
    decision_map = {d.anomaly_id: d for d in body.decisions}
    anom_rows = (
        await db.execute(select(Anomaly).where(Anomaly.session_id == session_id_uuid))
    ).scalars().all()

    for anom in anom_rows:
        dec = decision_map.get(str(anom.id))
        if dec:
            anom.user_action = dec.action
            anom.action_params = dec.params
            anom.resolved_at = now

    session_row.status = SessionStatus.PROCESSING
    await db.flush()

    provider = session_row.llm_provider or "gemini"

    # Commit NOW so the background task's fresh AsyncSession can see the
    # persisted decisions and the 'processing' status on all DB backends,
    # regardless of FastAPI's yield-dependency cleanup ordering.
    # Mirrors the explicit-commit invariant established above for /start.
    await db.commit()

    background_tasks.add_task(
        _run_phase23_background,
        session_id=body.session_id,
        decisions=decisions_raw,
        llm_provider=provider,
    )
    logger.info(
        "Phase 2+3 queued -- session=%s decisions=%d",
        body.session_id, len(decisions_raw),
    )
    return AnalyzeCompleteResponse(
        session_id=body.session_id,
        status=SessionStatus.PROCESSING.value,
        message="Phase 2+3 pipeline started. Poll GET /api/session/{id} for status.",
    )


# ---------------------------------------------------------------------------
# Background task -- Phase 2+3
# ---------------------------------------------------------------------------


async def _run_phase23_background(
    session_id: str,
    decisions: list[dict[str, Any]],
    llm_provider: str,
) -> None:
    """
    Run Phase 2 (Janitor + Engineer) and Phase 3 (Storyteller) pipeline.

    Execution runs through ai_engine/graph/workflow.py's phase2_app (a
    compiled LangGraph app). build_phase2_app() compiles a fresh graph per
    call whose three nodes (janitor, engineer, storyteller) close over this
    run's llm/auditor/processed_dir. It takes no db parameter -- ai_engine
    never touches the database directly (2026-07-03 architecture audit,
    decision log item 7); this function persists chart_specs/eda_narrative
    using its own `db` session below. Storyteller's node is the last to run
    and sets session.status -> 'complete' via Auditor.
    """
    try:
        async with AsyncSessionLocal() as db:
            session_row = await db.get(Session, uuid.UUID(session_id))
            try:
                if session_row is None:
                    logger.error("Phase 2+3: session %s not found", session_id)
                    return

                # Load raw file path
                file_row = (
                    await db.execute(
                        select(File).where(
                            File.session_id == uuid.UUID(session_id),
                            File.file_type == FileType.RAW,
                        ).limit(1)
                    )
                ).scalar_one_or_none()

                if file_row is None:
                    session_row.status = SessionStatus.ERROR
                    session_row.error_message = "Raw file record not found"
                    await db.commit()
                    return

                df = _read_dataframe(file_row.storage_path)
                renames: dict[str, str] = session_row.column_renames or {}
                if renames:
                    df = df.rename(columns=renames)

                # Load anomaly records from DB
                anom_rows = (
                    await db.execute(
                        select(Anomaly).where(Anomaly.session_id == uuid.UUID(session_id))
                    )
                ).scalars().all()
                anomaly_report: list[AnomalyRecord] = [_to_record(a) for a in anom_rows]

                state: dict[str, Any] = {
                    "session_id": session_id,
                    "llm_provider": llm_provider,
                    "df_working": df,
                    "anomaly_report": anomaly_report,
                    "user_decisions": decisions,
                    "user_intent": session_row.user_intent or "",
                    "quality_score_before": session_row.quality_score_before or 0.0,
                }

                settings = get_settings()
                auditor = Auditor(db=db, session_id=session_id)
                llm = get_llm_provider(
                    llm_provider,
                    default_provider=settings.llm_provider,
                    ollama_base_url=settings.ollama_base_url,
                    gemini_api_key=settings.gemini_api_key,
                )

                phase2_app = build_phase2_app(
                    llm=llm, auditor=auditor, processed_dir=settings.processed_dir,
                )
                state = await phase2_app.ainvoke(state)

                # Persist chart_specs and eda_narrative. This used to happen
                # inside storyteller.run_storyteller() itself; it now happens
                # here so ai_engine never imports backend.db.models
                # (2026-07-03 architecture audit, decision log item 7).
                await _persist_charts(state.get("chart_specs", []), session_id, db)

                # Patch quality_score_after and narrative on session row
                if session_row is not None:
                    session_row.quality_score_after = state.get("quality_score_after")
                    narrative = state.get("eda_narrative")
                    if narrative is not None:
                        # Sanitise before serialising -- prevents NaN in stored JSON
                        session_row.narrative = json.dumps(sanitize_json(narrative))

                await db.commit()
                logger.info("Phase 2+3 done -- session=%s", session_id)

            except Exception as exc:
                logger.error(
                    "Unhandled error in Phase 2+3 background task session=%s: %s",
                    session_id, exc, exc_info=True,
                )
                if session_row is not None:
                    session_row.status = SessionStatus.ERROR
                    session_row.error_message = str(exc)[:500]
                await db.commit()
    except Exception as exc:
        logger.error("Phase 2+3 background task DB init failed session=%s: %s", session_id, exc)


# ---------------------------------------------------------------------------
# Helpers -- Phase 2+3
# ---------------------------------------------------------------------------

def _read_dataframe(path: str) -> pd.DataFrame:
    """Load CSV or Excel, trying each encoding in CSV_ENCODING_FALLBACKS for CSV files."""
    p = Path(path)
    if p.suffix.lower() != ".csv":
        return pd.read_excel(p)
    for encoding in CSV_ENCODING_FALLBACKS:
        try:
            return pd.read_csv(p, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {p} with any of: {CSV_ENCODING_FALLBACKS}")


def _to_record(anom: Anomaly) -> AnomalyRecord:
    return {
        "anomaly_id": str(anom.id),
        "anomaly_type": anom.anomaly_type.value,
        "column_name": anom.column_name,
        "affected_rows": anom.affected_rows,
        "null_rate": anom.null_rate,
        "severity": anom.severity.value,
        "details": anom.details or {},
        "display_order": anom.display_order,
        "is_supplementary": False,
    }


async def _persist_charts(
    specs: list[ChartSpec],
    session_id: str,
    db: AsyncSession,
) -> None:
    """
    Write each ChartSpec to the charts table and flush.

    Moved here from ai_engine/agents/storyteller.py so that ai_engine never
    imports backend.db.models directly (2026-07-03 architecture audit,
    decision log item 7). Does not commit -- the caller's transaction
    boundary controls when the commit happens.
    """
    sid = uuid.UUID(session_id)
    for spec in specs:
        cols: list[str] = []
        if spec.get("x_column"):
            cols.append(spec["x_column"])  # type: ignore[arg-type]
        if spec.get("y_column"):
            cols.append(spec["y_column"])  # type: ignore[arg-type]
        if spec.get("color_column"):
            cols.append(spec["color_column"])  # type: ignore[arg-type]
        row = Chart(
            id=uuid.UUID(spec["chart_id"]),
            session_id=sid,
            chart_type=spec["chart_type"],
            title=spec["title"],
            plotly_config=spec["plotly_config"],
            insight_text=spec.get("insight_text", ""),
            columns_used=cols,
            display_order=spec["display_order"],
        )
        db.add(row)
    await db.flush()
