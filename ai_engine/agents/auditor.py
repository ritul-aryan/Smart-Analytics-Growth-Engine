"""
ai_engine/agents/auditor.py

Cross-cutting audit logger — the transparency and trust layer for MAE.

Every transformation applied by any agent must be logged here with a
human-readable reason string.  The audit_log table is a core product
feature, not optional infrastructure.  SME users read this log to
understand exactly what the AI did to their data and why.

Usage in agent code:

    auditor = Auditor(db=db_session, session_id=state["session_id"])

    await auditor.log(
        agent_name="janitor",
        phase="phase2",
        action="Dropped 47 duplicate rows",
        reason="User selected remove_duplicates for DUPLICATE_ROWS anomaly",
        rows_affected=47,
        is_llm_decision=False,
    )

Design rules:
    - Audit writes are fire-and-log: a write failure is logged at ERROR
      level but never raises, so a DB hiccup does not abort the pipeline.
    - Writes are immediate (no batching) so the log is accurate up to the
      point of any failure.
    - log_batch() flushes all entries in a single transaction for
      high-volume phases (e.g. Phase 1 anomaly detection).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AuditLog, Session as SessionModel, SessionStatus

logger = logging.getLogger(__name__)

# Valid agent names — used in log entries and the UI filter
AGENT_NAMES = frozenset({
    "orchestrator",
    "profiler",
    "janitor",
    "engineer",
    "storyteller",
    "auditor",
})

# Valid phase identifiers
PHASE_IDS = frozenset({"phase1", "phase2", "phase2_5", "phase3"})


@dataclass
class AuditEntry:
    """
    A single pending audit log entry.

    Used by log_batch() to accumulate entries before a bulk write.
    Instantiated directly only inside the Auditor — callers use log()
    or log_batch() instead.
    """

    agent_name: str
    phase: str
    action: str
    reason: str
    column_affected: str | None = None
    rows_affected: int = 0
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    is_llm_decision: bool = False
    llm_prompt_summary: str | None = None


class Auditor:
    """
    Writes agent actions to the audit_log table and manages session status.

    One Auditor instance is created per pipeline run and passed to every
    agent that needs to log.  It holds a reference to the open AsyncSession
    for the duration of the run.
    """

    def __init__(self, db: AsyncSession, session_id: str) -> None:
        """
        Initialise the auditor for a specific session.

        Args:
            db:         Open AsyncSession.  The auditor does not own this
                        session — it never commits or closes it.
            session_id: UUID string of the active sessions row.
        """
        self._db = db
        self._session_id: UUID = UUID(session_id)

    async def log(
        self,
        agent_name: str,
        phase: str,
        action: str,
        reason: str,
        *,
        column_affected: str | None = None,
        rows_affected: int = 0,
        before_value: dict[str, Any] | None = None,
        after_value: dict[str, Any] | None = None,
        is_llm_decision: bool = False,
        llm_prompt_summary: str | None = None,
    ) -> None:
        """
        Write a single audit entry to the database immediately.

        A write failure is caught, logged at ERROR level, and swallowed —
        a DB hiccup must never abort the agent pipeline.

        Args:
            agent_name:          Name of the agent performing the action.
                                 Must be one of: orchestrator, profiler,
                                 janitor, engineer, storyteller.
            phase:               Pipeline phase: phase1 | phase2 |
                                 phase2_5 | phase3.
            action:              Short description (≤255 chars), e.g.
                                 'Dropped 47 duplicate rows'.
            reason:              Human-readable explanation for SME users,
                                 e.g. 'User selected remove_duplicates'.
            column_affected:     Column name if the action targets one
                                 column; None for row-level actions.
            rows_affected:       Number of rows modified or examined.
            before_value:        Sample of data before the change (JSON).
            after_value:         Sample of data after the change (JSON).
            is_llm_decision:     True if this action was driven by LLM output.
            llm_prompt_summary:  Brief summary of the prompt sent to the LLM.
        """
        entry = AuditEntry(
            agent_name=agent_name,
            phase=phase,
            action=action,
            reason=reason,
            column_affected=column_affected,
            rows_affected=rows_affected,
            before_value=before_value,
            after_value=after_value,
            is_llm_decision=is_llm_decision,
            llm_prompt_summary=llm_prompt_summary,
        )
        await self._write_entries([entry])

    async def log_batch(self, entries: list[AuditEntry]) -> None:
        """
        Write multiple audit entries in a single database flush.

        Use this for high-volume phases (e.g. Phase 1 anomaly detection)
        to avoid many individual round-trips to the database.

        Args:
            entries: List of AuditEntry dataclass instances to persist.
        """
        if not entries:
            return
        await self._write_entries(entries)

    async def update_session_status(
        self,
        status: str,
        *,
        error_message: str | None = None,
        quality_score_before: float | None = None,
        quality_score_after: float | None = None,
    ) -> None:
        """
        Update the status and optional scalar fields on the sessions row.

        Args:
            status:               New status value: 'upload' | 'audit' |
                                 'processing' | 'complete' | 'error'.
                                 Accepts a plain string (not the SessionStatus
                                 enum) so that agent modules calling this
                                 method (orchestrator, storyteller) do not
                                 need to import backend.db.models themselves
                                 -- Auditor is the one file in ai_engine that
                                 legitimately owns that import (2026-07-03
                                 architecture audit, decision log item 7).
                                 Coerced to SessionStatus here, so an invalid
                                 value raises ValueError immediately.
            error_message:        Populated when status='error'.
            quality_score_before: Set after Phase 1 scoring completes.
            quality_score_after:  Set after Phase 2 cleaning completes.
        """
        status_enum = SessionStatus(status)
        try:
            session_row = await self._db.get(SessionModel, self._session_id)
            if session_row is None:
                logger.error(
                    "update_session_status: session %s not found in DB", self._session_id
                )
                return

            session_row.status = status_enum
            session_row.updated_at = datetime.now(timezone.utc)

            if error_message is not None:
                session_row.error_message = error_message
            if quality_score_before is not None:
                session_row.quality_score_before = quality_score_before
            if quality_score_after is not None:
                session_row.quality_score_after = quality_score_after

            await self._db.flush()
            logger.info(
                "Session %s status → %s", self._session_id, status_enum.value
            )
        except Exception as exc:
            logger.error(
                "Failed to update session %s status to %s: %s",
                self._session_id,
                status_enum.value,
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _write_entries(self, entries: list[AuditEntry]) -> None:
        """
        Persist a list of AuditEntry objects to the audit_log table.

        Converts each dataclass to an AuditLog ORM row, adds them all to
        the session, and flushes.  Does not commit — the caller's transaction
        boundary controls when the commit happens.

        On any exception the error is logged and swallowed so that audit
        failures never abort the pipeline.
        """
        try:
            rows = [
                AuditLog(
                    id=uuid4(),
                    session_id=self._session_id,
                    agent_name=entry.agent_name,
                    phase=entry.phase,
                    action=entry.action[:255],   # Enforce column width
                    reason=entry.reason,
                    column_affected=entry.column_affected,
                    rows_affected=entry.rows_affected,
                    before_value=entry.before_value,
                    after_value=entry.after_value,
                    is_llm_decision=entry.is_llm_decision,
                    llm_prompt_summary=entry.llm_prompt_summary,
                    timestamp=datetime.now(timezone.utc),
                )
                for entry in entries
            ]
            self._db.add_all(rows)
            await self._db.flush()
            logger.debug(
                "Auditor wrote %d entr%s for session %s",
                len(rows),
                "y" if len(rows) == 1 else "ies",
                self._session_id,
            )
        except Exception as exc:
            logger.error(
                "Audit write failed for session %s (%d entries): %s",
                self._session_id,
                len(entries),
                exc,
            )
      