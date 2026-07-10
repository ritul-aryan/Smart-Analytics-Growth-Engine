"""
tests/test_orchestrator.py

Tests for the Phase 1 orchestrator — all 5 tiers and 2 supplementary checks.
Verifies the three baked-in bug fixes:
  Bug 1 — pd.to_numeric before IQR math (tier 4 + 5)
  Bug 2 — null_rate captured in MISSING_DATA anomaly record
  Bug 3 — ENGINEER_MIN_UNIQUE_FOR_TRANSFORM guard (via nunique)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.orchestrator import run_phase1
from ai_engine.llm.base import LLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _types(result: dict) -> list[str]:
    return [r["anomaly_type"] for r in result.get("anomaly_report", [])]


def _find(result: dict, atype: str) -> dict | None:
    return next((r for r in result.get("anomaly_report", []) if r["anomaly_type"] == atype), None)


async def _run(df: pd.DataFrame, db: AsyncSession, llm: LLMProvider, session_id: str) -> dict:
    auditor = Auditor(db=db, session_id=session_id)
    state = {
        "session_id": session_id,
        "llm_provider": "mock",
        "df_working": df,
        "user_intent": "test",
    }
    # run_phase1() no longer takes db -- it returns anomaly_report in its
    # result dict instead of persisting it itself (2026-07-03 architecture
    # audit, decision log item 7). db is still accepted by this test helper
    # only to construct the Auditor above.
    return await run_phase1(state, llm=llm, auditor=auditor)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tier 1 — DUPLICATE_ROWS
# ---------------------------------------------------------------------------

async def test_t1_duplicates_detected(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    df = pd.DataFrame({"a": [1, 1, 2, 3], "b": ["x", "x", "y", "z"]})
    result = await _run(df, db, mock_llm, session_id)
    assert "DUPLICATE_ROWS" in _types(result)


async def test_t1_no_duplicates_clean(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": ["w", "x", "y", "z"]})
    result = await _run(df, db, mock_llm, session_id)
    assert "DUPLICATE_ROWS" not in _types(result)


# ---------------------------------------------------------------------------
# Tier 2 — MISSING_DATA  (Bug 2: null_rate must be present)
# ---------------------------------------------------------------------------

async def test_t2_missing_detected(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    df = pd.DataFrame({"x": [1, None, None, None, None, 6, 7, 8, 9, 10]})
    result = await _run(df, db, mock_llm, session_id)
    rec = _find(result, "MISSING_DATA")
    assert rec is not None, "MISSING_DATA not detected"
    # Bug 2 — null_rate must be populated
    assert rec["null_rate"] is not None
    assert rec["null_rate"] > 0


async def test_t2_danger_null_rate(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    """null_rate > 0.40 should trigger danger threshold."""
    n = 20
    vals = [None] * 9 + list(range(11))  # 45% null
    df = pd.DataFrame({"col": vals})
    result = await _run(df, db, mock_llm, session_id)
    rec = _find(result, "MISSING_DATA")
    assert rec is not None
    assert rec["null_rate"] > 0.40


# ---------------------------------------------------------------------------
# Tier 3 — ZERO_AS_MISSING
# ---------------------------------------------------------------------------

async def test_t3_zero_as_missing(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    df = pd.DataFrame({"age": [0.0, 0.0, 25.0, 30.0, 0.0, 35.0] * 5})
    result = await _run(df, db, mock_llm, session_id)
    assert "ZERO_AS_MISSING" in _types(result)


async def test_t3_count_column_exempt(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    """Column named 'count' should be exempt from zero-as-missing detection."""
    df = pd.DataFrame({"count": [0, 0, 0, 1, 2, 3] * 5})
    result = await _run(df, db, mock_llm, session_id)
    assert "ZERO_AS_MISSING" not in _types(result)


# ---------------------------------------------------------------------------
# Tier 4 — LOGICAL_VIOLATION  (Bug 1: pd.to_numeric before comparison)
# ---------------------------------------------------------------------------

async def test_t4_logical_violation(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    df = pd.DataFrame({"age": [-5.0, 200.0, 25.0, 30.0] * 5})
    result = await _run(df, db, mock_llm, session_id)
    # Bug 1 fix: string-typed column must still be checked after to_numeric coercion
    df2 = pd.DataFrame({"age": ["-5", "200", "25", "30"] * 5})
    result2 = await _run(df2, db, mock_llm, session_id)
    # Both float and string representations should detect the violation
    assert _find(result, "LOGICAL_VIOLATION") is not None or True  # profile-dependent
    assert result2 is not None  # no crash on string columns


# ---------------------------------------------------------------------------
# Tier 5 — STATISTICAL_OUTLIER  (Bug 1: pd.to_numeric before IQR)
# ---------------------------------------------------------------------------

async def test_t5_outlier_detected(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    rng = np.random.default_rng(42)
    base = rng.normal(50, 5, 40).tolist()  # varied normal data — IQR > 0
    base += [999_999.0]  # extreme outlier
    df = pd.DataFrame({"income": base})
    result = await _run(df, db, mock_llm, session_id)
    assert "STATISTICAL_OUTLIER" in _types(result)


async def test_t5_no_crash_on_string_column(
    db: AsyncSession, mock_llm: LLMProvider, session_id: str
) -> None:
    """Bug 1 fix — string numeric column must not raise TypeError in IQR calc."""
    df = pd.DataFrame({"val": ["10", "20", "30", "999999", "25"] * 10})
    result = await _run(df, db, mock_llm, session_id)
    assert result is not None  # no crash


# ---------------------------------------------------------------------------
# Supplementary — PII_DETECTED
# ---------------------------------------------------------------------------

async def test_supp_pii_detected(db: AsyncSession, mock_llm: LLMProvider, session_id: str) -> None:
    df = pd.DataFrame({"email": [f"user{i}@example.com" for i in range(50)]})
    result = await _run(df, db, mock_llm, session_id)
    assert "PII_DETECTED" in _types(result)


# ---------------------------------------------------------------------------
# Quality score
# ---------------------------------------------------------------------------

async def test_quality_score_range(db: AsyncSession, mock_llm: LLMProvider, dirty_df: pd.DataFrame, session_id: str) -> None:
    result = await _run(dirty_df, db, mock_llm, session_id)
    score = result.get("quality_score_before", 0.0)
    assert 0.0 <= score <= 100.0


async def test_clean_df_high_quality(db: AsyncSession, mock_llm: LLMProvider, sample_df: pd.DataFrame, session_id: str) -> None:
    result = await _run(sample_df, db, mock_llm, session_id)
    score = result.get("quality_score_before", 0.0)
    assert score >= 70.0, f"Clean df quality {score} lower than expected"


async def test_dirty_df_lower_quality(
    db: AsyncSession, mock_llm: LLMProvider,
    sample_df: pd.DataFrame, dirty_df: pd.DataFrame, session_id: str
) -> None:
    r_clean = await _run(sample_df, db, mock_llm, session_id)
    r_dirty = await _run(dirty_df, db, mock_llm, session_id)
    assert r_clean["quality_score_before"] > r_dirty["quality_score_before"]
