"""
tests/test_storyteller.py

Tests for the Phase 3 Storyteller agent.
Verifies chart generation, narrative structure, LLM-failure fallback, the
session.status -> 'complete' transition via Auditor, and that chart/narrative
persistence correctly does NOT happen inside run_storyteller() itself (moved
to backend/api/analyze.py -- 2026-07-03 architecture audit, decision log
item 7).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.storyteller import run_storyteller
from ai_engine.graph.state import GraphState
from ai_engine.llm.base import LLMProvider
from backend.db.models import Chart, Session, SessionStatus


async def _make_session(db: AsyncSession, session_id: str) -> None:
    """Insert a minimal Session row so storyteller can patch status."""
    import uuid
    row = Session(
        id=uuid.UUID(session_id),
        original_filename="test.csv",
        stored_filename="test.csv",
        status=SessionStatus.PROCESSING,
    )
    db.add(row)
    await db.flush()


def _state(df, session_id: str) -> GraphState:
    return {  # type: ignore[return-value]
        "session_id": session_id,
        "df_clean": df,
        "user_intent": "predict income from age",
    }


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

async def test_charts_generated(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    assert len(result["chart_specs"]) >= 1


async def test_histograms_and_boxes_present(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    types = [s["chart_type"] for s in result["chart_specs"]]
    assert "histogram" in types
    assert "box" in types


async def test_correlation_heatmap_present(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    types = [s["chart_type"] for s in result["chart_specs"]]
    # sample_df has multiple numeric cols → heatmap expected
    assert "heatmap" in types


async def test_charts_not_persisted_by_storyteller_itself(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    """
    run_storyteller() must NOT write to the charts table itself.

    Persisting chart_specs to the database moved to
    backend/api/analyze.py's _persist_charts() (2026-07-03 architecture
    audit, decision log item 7), specifically so ai_engine never imports
    backend.db.models directly. This test guards against that persistence
    logic silently creeping back into the agent.
    """
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    assert len(result["chart_specs"]) >= 1
    chart_rows = (await db.execute(select(Chart))).scalars().all()
    assert len(chart_rows) == 0


# ---------------------------------------------------------------------------
# Narrative structure
# ---------------------------------------------------------------------------

async def test_narrative_keys(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    nar = result["eda_narrative"]
    for key in (
        "top_correlations", "missingness_hotspots",
        "ml_readiness_score", "ml_readiness_notes",
        "intent_recommendation", "row_count", "col_count",
        "numeric_cols", "categorical_cols", "datetime_cols",
    ):
        assert key in nar, f"Narrative missing key: {key}"


async def test_narrative_ml_readiness_range(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    score = result["eda_narrative"]["ml_readiness_score"]
    assert 0.0 <= score <= 100.0


async def test_narrative_top_correlations(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    corrs = result["eda_narrative"]["top_correlations"]
    assert isinstance(corrs, list)
    assert len(corrs) <= 3
    for c in corrs:
        assert "col_a" in c and "col_b" in c and "spearman_r" in c


async def test_narrative_intent_recommendation(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    """Intent 'predict income' → recommendation mentions predictive modelling."""
    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    rec = result["eda_narrative"]["intent_recommendation"]
    assert "predict" in rec.lower() or "modelling" in rec.lower() or "regression" in rec.lower()


# ---------------------------------------------------------------------------
# Session status patched to 'complete'
# ---------------------------------------------------------------------------

async def test_session_status_complete(
    db: AsyncSession, mock_llm: LLMProvider, auditor: Auditor,
    sample_df, session_id: str,
) -> None:
    import uuid
    await _make_session(db, session_id)
    await run_storyteller(_state(sample_df, session_id), llm=mock_llm, auditor=auditor)
    row = await db.get(Session, uuid.UUID(session_id))
    assert row is not None
    assert row.status == SessionStatus.COMPLETE  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# LLM failure fallback
# ---------------------------------------------------------------------------

async def test_llm_failure_does_not_crash(
    db: AsyncSession, auditor: Auditor, sample_df, session_id: str,
) -> None:
    """If LLM throws, storyteller should skip primary chart but still return others."""

    class _FailLLM(LLMProvider):
        @property
        def name(self) -> str:
            return "fail"

        async def complete(self, prompt: str, *, task: str = "general") -> str:
            raise RuntimeError("LLM unavailable")

        async def complete_json(self, prompt: str, *, task: str = "general") -> dict:
            raise RuntimeError("LLM unavailable")

    await _make_session(db, session_id)
    result = await run_storyteller(_state(sample_df, session_id), llm=_FailLLM(), auditor=auditor)
    # Should still have deterministic charts
    assert len(result["chart_specs"]) >= 1
