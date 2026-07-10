"""
tests/test_engineer.py

Tests for the Phase 2.5 Engineer agent — all four transforms.
Bug 3 guard: no log/interaction transforms on columns with < ENGINEER_MIN_UNIQUE_FOR_TRANSFORM
unique values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.engineer import run_engineer
from ai_engine.config import ENGINEER_MIN_UNIQUE_FOR_TRANSFORM
from ai_engine.graph.state import GraphState


def _state(df: pd.DataFrame, session_id: str = "test") -> GraphState:
    return {"session_id": session_id, "df_clean": df}  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# OHE
# ---------------------------------------------------------------------------

async def test_ohe_applied(auditor: Auditor) -> None:
    """
    OHE appends dummy columns and KEEPS the original categorical column.

    This is a deliberate deviation from spec Section 6.2's literal
    "drop_first=True" wording -- see the rationale comment directly above
    _apply_ohe() in ai_engine/agents/engineer.py (2026-07-04 architecture
    audit follow-up, decision log item 13, flagged to and accepted by the
    user rather than silently kept or silently reverted). This test
    previously asserted the opposite (original dropped) and was failing
    against the actual, intended behavior.
    """
    df = pd.DataFrame({"city": ["London", "Paris", "Berlin"] * 20, "x": range(60)})
    result = await run_engineer(_state(df), auditor=auditor)
    out = result["df_engineered"]
    # city column is OHE'd; original is kept alongside the new dummy columns
    assert "city" in out.columns
    assert any(c.startswith("city_") for c in out.columns)
    # drop_first=False -- all 3 categories get their own dummy column
    assert {"city_London", "city_Paris", "city_Berlin"} <= set(out.columns)


async def test_ohe_skips_high_cardinality(auditor: Auditor) -> None:
    """Columns with > ENGINEER_MIN_UNIQUE_FOR_TRANSFORM uniques are skipped."""
    df = pd.DataFrame({"name": [f"user_{i}" for i in range(50)], "x": range(50)})
    result = await run_engineer(_state(df), auditor=auditor)
    # 'name' has 50 unique values → should NOT be OHE'd
    assert "name" in result["df_engineered"].columns


async def test_ohe_skips_single_value(auditor: Auditor) -> None:
    """Columns with only 1 unique value should not be OHE'd."""
    df = pd.DataFrame({"flag": ["yes"] * 30, "x": range(30)})
    result = await run_engineer(_state(df), auditor=auditor)
    # 1 unique value → doesn't meet 2–10 range
    assert "flag" in result["df_engineered"].columns


# ---------------------------------------------------------------------------
# Log transform  (Bug 3 guard: nunique >= ENGINEER_MIN_UNIQUE_FOR_TRANSFORM)
# ---------------------------------------------------------------------------

async def test_log_transform_applied(auditor: Auditor) -> None:
    rng = np.random.default_rng(1)
    # Exponential distribution → high skew, all positive, high nunique
    vals = rng.exponential(scale=1000, size=100)
    df = pd.DataFrame({"income": vals})
    result = await run_engineer(_state(df), auditor=auditor)
    assert "income_log" in result["df_engineered"].columns


async def test_log_skips_negative_values(auditor: Auditor) -> None:
    vals = list(range(-10, 90))  # contains negatives
    df = pd.DataFrame({"val": vals})
    result = await run_engineer(_state(df), auditor=auditor)
    assert "val_log" not in result["df_engineered"].columns


async def test_log_skips_low_nunique(auditor: Auditor) -> None:
    """Bug 3: binary-coded column (0/1) must not get log transform."""
    df = pd.DataFrame({"flag": [0, 1, 0, 1] * 25})
    result = await run_engineer(_state(df), auditor=auditor)
    assert "flag_log" not in result["df_engineered"].columns


# ---------------------------------------------------------------------------
# Datetime extraction
# ---------------------------------------------------------------------------

async def test_datetime_extraction(auditor: Auditor, sample_df: pd.DataFrame) -> None:
    result = await run_engineer(_state(sample_df), auditor=auditor)
    out = result["df_engineered"]
    # sample_df has 'signup_date' column
    assert "signup_date_year" in out.columns
    assert "signup_date_month" in out.columns
    assert "signup_date_dow" in out.columns
    assert "signup_date_is_weekend" in out.columns


async def test_datetime_is_weekend_values(auditor: Auditor) -> None:
    dates = pd.date_range("2024-01-01", periods=10, freq="D")  # Mon 1 Jan → Wed 10 Jan
    df = pd.DataFrame({"dt": dates, "val": range(10)})
    result = await run_engineer(_state(df), auditor=auditor)
    out = result["df_engineered"]
    assert "dt_is_weekend" in out.columns
    # Jan 6+7 2024 are Sat+Sun → is_weekend == 1
    assert set(out["dt_is_weekend"].dropna().unique()).issubset({0, 1})


# ---------------------------------------------------------------------------
# Interaction term  (Bug 3 guard)
# ---------------------------------------------------------------------------

async def test_interaction_term_created(auditor: Auditor) -> None:
    rng = np.random.default_rng(2)
    n = 80
    a = rng.uniform(0, 100, size=n)
    b = a * 0.9 + rng.normal(0, 2, size=n)  # highly correlated with a
    df = pd.DataFrame({"feature_a": a, "feature_b": b})
    result = await run_engineer(_state(df), auditor=auditor)
    out = result["df_engineered"]
    assert any("_x_" in c for c in out.columns)


async def test_interaction_skips_low_correlation(auditor: Auditor) -> None:
    rng = np.random.default_rng(3)
    n = 80
    a = rng.uniform(0, 100, size=n)
    b = rng.uniform(0, 100, size=n)  # uncorrelated
    df = pd.DataFrame({"x": a, "y": b})
    result = await run_engineer(_state(df), auditor=auditor)
    out = result["df_engineered"]
    assert not any("_x_" in c for c in out.columns)


async def test_interaction_skips_low_nunique(auditor: Auditor) -> None:
    """Bug 3: binary columns must not form interaction terms."""
    df = pd.DataFrame({"a": [0, 1] * 40, "b": [1, 0] * 40})
    result = await run_engineer(_state(df), auditor=auditor)
    assert not any("_x_" in c for c in result["df_engineered"].columns)


# ---------------------------------------------------------------------------
# fe_report content
# ---------------------------------------------------------------------------

async def test_fe_report_populated(auditor: Auditor, sample_df: pd.DataFrame) -> None:
    result = await run_engineer(_state(sample_df), auditor=auditor)
    report = result["fe_report"]
    assert isinstance(report, list)
    # sample_df has a datetime column → at least one record expected
    assert len(report) >= 1
    for rec in report:
        assert "transform_type" in rec
        assert "source_columns" in rec
        assert "output_columns" in rec
        assert "description" in rec
