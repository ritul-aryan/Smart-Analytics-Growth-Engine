"""Initial schema — all 6 MAE tables.

Creates sessions, anomalies, audit_log, files, charts, and chat_messages
in dependency order.  All tables from Section 5 of the master architecture
document are created in this single migration as required.

Revision ID: 0001
Revises:
Create Date: 2026-06-26 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Portable server-default timestamp — works in both SQLite and PostgreSQL
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    """Create all 6 tables in dependency order."""

    # ------------------------------------------------------------------
    # 1. sessions — no foreign key dependencies
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        # Enum stored as VARCHAR — portable across SQLite and PostgreSQL
        sa.Column("status", sa.String(length=20), nullable=False, server_default="upload"),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("user_intent", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(length=50), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("col_count", sa.Integer(), nullable=True),
        sa.Column("quality_score_before", sa.Float(), nullable=True),
        sa.Column("quality_score_after", sa.Float(), nullable=True),
        sa.Column("column_renames", sa.JSON(), nullable=True),
        sa.Column("metadata_summary", sa.Text(), nullable=True),
        # narrative: intentional addition beyond Section 5.1's sessions field
        # list -- persists Storyteller's programmatic narrative (Section 6.3)
        # so it survives page refresh (Section 4.4 Chat tab requirement).
        # See backend/db/models.py Session.narrative for full rationale
        # (2026-07-03 architecture audit, decision log item 5).
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )

    # ------------------------------------------------------------------
    # 2. anomalies — depends on sessions
    # ------------------------------------------------------------------
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_type", sa.String(length=50), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("affected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("null_rate", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("user_action", sa.String(length=50), nullable=True),
        sa.Column("action_params", sa.JSON(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_anomalies_session_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_anomalies"),
    )

    # ------------------------------------------------------------------
    # 3. audit_log — depends on sessions
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("column_affected", sa.String(length=255), nullable=True),
        sa.Column("rows_affected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("before_value", sa.JSON(), nullable=True),
        sa.Column("after_value", sa.JSON(), nullable=True),
        sa.Column("is_llm_decision", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("llm_prompt_summary", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_audit_log_session_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )

    # ------------------------------------------------------------------
    # 4. files — depends on sessions
    # ------------------------------------------------------------------
    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("col_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_files_session_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
    )

    # ------------------------------------------------------------------
    # 5. charts — depends on sessions
    # ------------------------------------------------------------------
    op.create_table(
        "charts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("chart_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("plotly_config", sa.JSON(), nullable=False),
        sa.Column("insight_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("columns_used", sa.JSON(), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("custom_prompt", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_charts_session_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_charts"),
    )

    # ------------------------------------------------------------------
    # 6. chat_messages — depends on sessions AND charts
    # ------------------------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("has_chart", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("chart_id", sa.Uuid(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_chat_messages_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chart_id"],
            ["charts.id"],
            name="fk_chat_messages_chart_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
    )


def downgrade() -> None:
    """Drop all 6 tables in reverse dependency order."""
    op.drop_table("chat_messages")
    op.drop_table("charts")
    op.drop_table("files")
    op.drop_table("audit_log")
    op.drop_table("anomalies")
    op.drop_table("sessions")
