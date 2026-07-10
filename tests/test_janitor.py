"""
tests/test_janitor.py

Tests for the Phase 2 Janitor agent.
Verifies every action type and checks that quality_score_after
is recalculated correctly after decisions are applied.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.janitor import run_janitor
from ai_engine.graph.state import GraphState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(
    df: pd.DataFrame,
    decisions: list[dict],
    anomaly_report: list[dict] | None = None,
    session_id: str = "test-session-id",
) -> GraphState:
    return {  # type: ignore[return-value]
        "session_id": session_id,
        "df_working": df,
        "user_decisions": decisions,
        "anomaly_report": anomaly_report or [],
        "quality_score_before": 60.0,
    }


def _anomaly(
    aid: str,
    atype: str,
    col: str | None = None,
    affected: int = 5,
    details: dict | None = None,
    null_rate: float | None = None,
) -> dict:
    return {
        "anomaly_id": aid,
        "anomaly_type": atype,
        "column_name": col,
        "affected_rows": affected,
        "null_rate": null_rate,
        "severity": "medium",
        "details": details or {},
        "display_order": 1,
        "is_supplementary": False,
    }


# ---------------------------------------------------------------------------
# keep_as_is / keep_all — no rows removed
# ---------------------------------------------------------------------------

async def test_keep_as_is_no_change(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [1, 2, None, 4, 5]})
    a = _anomaly("a1", "MISSING_DATA", "x", null_rate=0.2)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "keep_as_is"}], [a]), auditor=auditor)
    assert len(result["df_clean"]) == 5
    assert result["df_clean"]["x"].isna().sum() == 1


# ---------------------------------------------------------------------------
# remove_duplicates
# ---------------------------------------------------------------------------

async def test_remove_duplicates(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [1, 1, 2, 3], "y": ["a", "a", "b", "c"]})
    a = _anomaly("a1", "DUPLICATE_ROWS", affected=1)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "remove_duplicates"}], [a]), auditor=auditor)
    assert len(result["df_clean"]) == 3


# ---------------------------------------------------------------------------
# drop_rows — MISSING_DATA
# ---------------------------------------------------------------------------

async def test_drop_rows_missing(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [1.0, None, 3.0, None, 5.0]})
    a = _anomaly("a1", "MISSING_DATA", "x", null_rate=0.4)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "drop_rows"}], [a]), auditor=auditor)
    assert result["df_clean"]["x"].isna().sum() == 0
    assert len(result["df_clean"]) == 3


# ---------------------------------------------------------------------------
# drop_rows — STATISTICAL_OUTLIER
# ---------------------------------------------------------------------------

async def test_drop_rows_outlier(auditor: Auditor) -> None:
    vals = [10.0] * 20 + [999_999.0]
    df = pd.DataFrame({"income": vals})
    a = _anomaly("a1", "STATISTICAL_OUTLIER", "income", details={"lower_fence": 0.0, "upper_fence": 50.0})
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "drop_rows"}], [a]), auditor=auditor)
    assert 999_999.0 not in result["df_clean"]["income"].values


# ---------------------------------------------------------------------------
# fill_mean / fill_median / fill_mode
# ---------------------------------------------------------------------------

async def test_fill_mean(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [10.0, 20.0, None, 40.0, None]})
    a = _anomaly("a1", "MISSING_DATA", "x", null_rate=0.4)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "fill_mean"}], [a]), auditor=auditor)
    assert result["df_clean"]["x"].isna().sum() == 0
    expected_mean = pd.Series([10.0, 20.0, 40.0]).mean()
    assert abs(result["df_clean"]["x"].iloc[2] - expected_mean) < 0.01


async def test_fill_median(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [10.0, None, 30.0, None, 50.0]})
    a = _anomaly("a1", "MISSING_DATA", "x", null_rate=0.4)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "fill_median"}], [a]), auditor=auditor)
    assert result["df_clean"]["x"].isna().sum() == 0


async def test_fill_mode(auditor: Auditor) -> None:
    df = pd.DataFrame({"city": ["London", None, "Paris", "London", None]})
    a = _anomaly("a1", "MISSING_DATA", "city", null_rate=0.4)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "fill_mode"}], [a]), auditor=auditor)
    assert result["df_clean"]["city"].isna().sum() == 0
    assert result["df_clean"]["city"].iloc[1] == "London"


# ---------------------------------------------------------------------------
# cap_iqr
# ---------------------------------------------------------------------------

async def test_cap_iqr(auditor: Auditor) -> None:
    df = pd.DataFrame({"val": [1.0, 2.0, 3.0, 999.0, 1000.0]})
    a = _anomaly("a1", "STATISTICAL_OUTLIER", "val", details={"lower_fence": 0.0, "upper_fence": 10.0})
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "cap_iqr"}], [a]), auditor=auditor)
    assert result["df_clean"]["val"].max() <= 10.0


# ---------------------------------------------------------------------------
# clamp_bounds
# ---------------------------------------------------------------------------

async def test_clamp_bounds(auditor: Auditor) -> None:
    df = pd.DataFrame({"age": [-5.0, 25.0, 200.0, 30.0]})
    a = _anomaly("a1", "LOGICAL_VIOLATION", "age", details={"min_bound": 0, "max_bound": 120})
    dec = {"anomaly_id": "a1", "action": "clamp_bounds", "params": {"min_bound": 0, "max_bound": 120}}
    result = await run_janitor(_state(df, [dec], [a]), auditor=auditor)
    assert result["df_clean"]["age"].min() >= 0
    assert result["df_clean"]["age"].max() <= 120


# ---------------------------------------------------------------------------
# redact / hash_sha256 / drop_column
# ---------------------------------------------------------------------------

async def test_redact(auditor: Auditor) -> None:
    df = pd.DataFrame({"email": [f"u{i}@test.com" for i in range(5)]})
    a = _anomaly("a1", "PII_DETECTED", "email")
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "redact"}], [a]), auditor=auditor)
    assert all(v == "[REDACTED]" for v in result["df_clean"]["email"])


async def test_hash_sha256(auditor: Auditor) -> None:
    df = pd.DataFrame({"email": [f"u{i}@test.com" for i in range(5)]})
    a = _anomaly("a1", "PII_DETECTED", "email")
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "hash_sha256"}], [a]), auditor=auditor)
    # SHA-256 hex digests are 64 chars
    assert all(len(v) == 64 for v in result["df_clean"]["email"])


async def test_drop_column(auditor: Auditor) -> None:
    df = pd.DataFrame({"email": ["a@b.com"] * 5, "age": [25] * 5})
    a = _anomaly("a1", "PII_DETECTED", "email")
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "drop_column"}], [a]), auditor=auditor)
    assert "email" not in result["df_clean"].columns


# ---------------------------------------------------------------------------
# quality_score_after
# ---------------------------------------------------------------------------

async def test_quality_improves_after_resolve(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [1.0, 1.0, 3.0, 4.0, 5.0]})
    a = _anomaly("a1", "DUPLICATE_ROWS", affected=1)
    state = _state(df, [{"anomaly_id": "a1", "action": "remove_duplicates"}], [a])
    state["quality_score_before"] = 80.0  # type: ignore[index]
    result = await run_janitor(state, auditor=auditor)
    # Resolved all anomalies → score should be 100
    assert result["quality_score_after"] == 100.0


async def test_changes_applied_list(auditor: Auditor) -> None:
    df = pd.DataFrame({"x": [1, 1, 2, 3]})
    a = _anomaly("a1", "DUPLICATE_ROWS", affected=1)
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "remove_duplicates"}], [a]), auditor=auditor)
    assert len(result["changes_applied"]) == 1
    assert result["changes_applied"][0]["action"] == "remove_duplicates"


# ---------------------------------------------------------------------------
# Bug 1 regression (Section 10.1) — IQR math crash on mixed-type columns
#
# Symptom in the prototype: "'<' not supported between instances of 'str'
# and 'float'". Root cause: a prior fill_mode action introduced string
# values into a numeric column, and the outlier handler's IQR comparison
# then failed because it compared strings against floats directly.
#
# Prevention: Janitor casts the affected column via
# pd.to_numeric(errors="coerce") before any IQR/comparison math (see
# _apply_decision's cap_iqr and drop_rows/STATISTICAL_OUTLIER branches).
# These tests exercise that exact scenario — a column of dtype=object
# holding a mix of real floats, numeric-looking strings, and a
# non-numeric string — and assert no exception is raised and the numeric
# comparison still behaves correctly. This closes the test-coverage gap
# flagged in the 2026-07-03 architecture audit (decision log item 10):
# the fix already existed in production code, but had no regression test.
# ---------------------------------------------------------------------------

async def test_cap_iqr_mixed_type_column_no_crash(auditor: Auditor) -> None:
    df = pd.DataFrame({"val": [1.0, 2.0, "3.0", "not_a_number", 999.0]}, dtype=object)
    a = _anomaly("a1", "STATISTICAL_OUTLIER", "val", details={"lower_fence": 0.0, "upper_fence": 10.0})
    # Must not raise "'<' not supported between instances of 'str' and 'float'"
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "cap_iqr"}], [a]), auditor=auditor)
    cleaned = pd.to_numeric(result["df_clean"]["val"], errors="coerce")
    assert cleaned.max() <= 10.0
    # The non-numeric string coerces to NaN rather than crashing the comparison
    assert cleaned.isna().sum() == 1


async def test_drop_rows_outlier_mixed_type_column_no_crash(auditor: Auditor) -> None:
    df = pd.DataFrame(
        {"income": [10.0, "20.0", 30.0, "not_numeric", 999_999.0]}, dtype=object
    )
    a = _anomaly(
        "a1", "STATISTICAL_OUTLIER", "income",
        details={"lower_fence": 0.0, "upper_fence": 50.0},
    )
    # Must not raise "'<' not supported between instances of 'str' and 'float'"
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "drop_rows"}], [a]), auditor=auditor)
    cleaned = pd.to_numeric(result["df_clean"]["income"], errors="coerce")
    assert 999_999.0 not in cleaned.values


async def test_fill_mean_outlier_mixed_type_column_no_crash(auditor: Auditor) -> None:
    """Same Bug 1 scenario via the fill_mean/inlier-mean path in _fill_missing,
    which also does IQR-fence comparisons on the raw column."""
    df = pd.DataFrame(
        {"income": [10.0, "20.0", 30.0, "not_numeric", 999_999.0]}, dtype=object
    )
    a = _anomaly(
        "a1", "STATISTICAL_OUTLIER", "income",
        details={"lower_fence": 0.0, "upper_fence": 50.0},
    )
    result = await run_janitor(_state(df, [{"anomaly_id": "a1", "action": "fill_mean"}], [a]), auditor=auditor)
    cleaned = pd.to_numeric(result["df_clean"]["income"], errors="coerce")
    assert 999_999.0 not in cleaned.values
