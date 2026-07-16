"""
backend/db/models.py — SQLAlchemy 2.0 ORM for all 6 MAE tables.

All tables live here and are created together in the initial Alembic
migration.  audit_log is a core product feature, not optional.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum as SAEnum, Float,
    ForeignKey, Integer, String, Text, Uuid, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all MAE ORM models."""


# ---------------------------------------------------------------------------
# Enumerations (stored as VARCHAR for SQLite / PostgreSQL portability)
# ---------------------------------------------------------------------------

class SessionStatus(str, enum.Enum):
    UPLOAD = "upload"
    AUDIT = "audit"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class AnomalyType(str, enum.Enum):
    DUPLICATE_ROWS = "DUPLICATE_ROWS"
    MISSING_DATA = "MISSING_DATA"
    ZERO_AS_MISSING = "ZERO_AS_MISSING"
    LOGICAL_VIOLATION = "LOGICAL_VIOLATION"
    STATISTICAL_OUTLIER = "STATISTICAL_OUTLIER"
    HIGH_NULL_DENSITY_ROWS = "HIGH_NULL_DENSITY_ROWS"
    PII_DETECTED = "PII_DETECTED"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FileType(str, enum.Enum):
    RAW = "raw"
    CLEAN = "clean"
    ENGINEERED = "engineered"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


def _enum(py_enum: type[enum.Enum]) -> SAEnum:
    return SAEnum(py_enum, native_enum=False)


# ---------------------------------------------------------------------------
# Model 1: sessions
# ---------------------------------------------------------------------------

class Session(Base):
    """One row per user analysis session."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
    status: Mapped[SessionStatus] = mapped_column(
        _enum(SessionStatus), nullable=False, default=SessionStatus.UPLOAD
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    user_intent: Mapped[str | None] = mapped_column(Text)
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    row_count: Mapped[int | None] = mapped_column(Integer)
    col_count: Mapped[int | None] = mapped_column(Integer)
    quality_score_before: Mapped[float | None] = mapped_column(Float)
    quality_score_after: Mapped[float | None] = mapped_column(Float)
    column_renames: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_summary: Mapped[str | None] = mapped_column(Text)
    # narrative: intentional addition beyond spec Section 5.1's sessions field
    # list (2026-07-03 architecture audit, decision log item 5). Section 6.3
    # requires Storyteller to "compute a programmatic narrative" (top-3
    # Spearman correlations, missingness hotspots, ML readiness, intent-
    # aligned recommendation) and Section 4.4's Chat tab spec requires "no
    # history loss on page refresh," which for the narrative means it must
    # be durably persisted rather than held only in GraphState. No other
    # column in Section 5.1 covers this, so `narrative` was added to close
    # that gap. Stored as a JSON string (via ai_engine.agents.storyteller.
    # sanitize_json + json.dumps in backend/api/analyze.py) rather than a
    # JSON column type, to match metadata_summary's existing Text pattern
    # on this same table. Kept, not reverted -- removing it would silently
    # break narrative persistence with no spec-compliant alternative.
    narrative: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    # PK-1: non-fatal Phase-1 warnings (e.g. profiler could not generate semantic
    # bounds because the LLM was unavailable). Nullable JSON list of strings.
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    # Revision Flow: when this session is a revision of an earlier one, points
    # to the parent session's id. NULL for original (first-run) sessions.
    parent_session_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    anomalies: Mapped[list["Anomaly"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )
    audit_entries: Mapped[list["AuditLog"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )
    files: Mapped[list["File"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )
    charts: Mapped[list["Chart"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )


# ---------------------------------------------------------------------------
# Model 2: anomalies
# ---------------------------------------------------------------------------

class Anomaly(Base):
    """One row per detected anomaly; stores detection result + HITL decision."""

    __tablename__ = "anomalies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    anomaly_type: Mapped[AnomalyType] = mapped_column(_enum(AnomalyType), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255))
    affected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    null_rate: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[Severity] = mapped_column(_enum(Severity), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    user_action: Mapped[str | None] = mapped_column(String(50))
    action_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped["Session"] = relationship(back_populates="anomalies")


# ---------------------------------------------------------------------------
# Model 3: audit_log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """One row per agent action — transparency layer for SME users."""

    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    column_affected: Mapped[str | None] = mapped_column(String(255))
    rows_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_llm_decision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_prompt_summary: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="audit_entries")


# ---------------------------------------------------------------------------
# Model 4: files
# ---------------------------------------------------------------------------

class File(Base):
    """Tracks every file version (raw / clean / engineered) for a session."""

    __tablename__ = "files"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    file_type: Mapped[FileType] = mapped_column(_enum(FileType), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    col_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="files")


# ---------------------------------------------------------------------------
# Model 5: charts
# ---------------------------------------------------------------------------

class Chart(Base):
    """Persisted Plotly chart specs — auto EDA portfolio + user custom charts."""

    __tablename__ = "charts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    chart_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    plotly_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    insight_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    columns_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    custom_prompt: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="charts")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="chart")


# ---------------------------------------------------------------------------
# Model 6: chat_messages
# ---------------------------------------------------------------------------

class ChatMessage(Base):
    """Persistent conversation history per session; links inline charts."""

    __tablename__ = "chat_messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    has_chart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chart_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("charts.id", ondelete="SET NULL")
    )
    token_count: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="chat_messages")
    chart: Mapped["Chart | None"] = relationship(back_populates="chat_messages")
