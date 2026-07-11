"""
ai_engine/agents/janitor.py — Phase 2 agent.

Reads user HITL decisions from GraphState, applies each transformation to
df_working in sequence, recalculates quality_score_after, saves clean CSV.
LLMs are NOT used here — all transformations are deterministic Pandas ops.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.orchestrator import _compute_quality_score
from ai_engine.config import (
    DEFAULT_NULL_DENSITY_ROW_THRESHOLD,
    JANITOR_CONTINUOUS_CARDINALITY_THRESHOLD,
    SEMANTIC_NONNEG_DOMAIN_PATTERNS,
)
from ai_engine.graph.state import AnomalyRecord, GraphState

logger = logging.getLogger(__name__)

# Fallback output directory, used only when a caller does not supply its own.
# Mirrors the LOCAL_PROCESSED_DIR default in .env.example (Section 11.5).
# Production callers (backend/api/analyze.py) resolve the real configured
# path from backend.config.Settings.processed_dir and pass it in explicitly
# -- ai_engine does not import backend directly (2026-07-03 architecture
# audit, decision log item 7).
_DEFAULT_PROCESSED_DIR = Path("./data/processed")


async def run_janitor(
    state: GraphState,
    *,
    auditor: Auditor,
    processed_dir: Path | str = _DEFAULT_PROCESSED_DIR,
) -> dict[str, Any]:
    """
    Apply HITL decisions; return df_clean, clean_file_path, quality_score_after.

    processed_dir: directory to save the clean CSV into. Callers resolve this
    from their own config (e.g. backend.config.Settings.processed_dir).
    """
    df: pd.DataFrame = state["df_working"].copy()  # type: ignore[index]
    anomaly_report: list[AnomalyRecord] = state.get("anomaly_report", [])  # type: ignore[assignment]
    user_decisions: list[dict[str, Any]] = state.get("user_decisions", [])  # type: ignore[assignment]

    # Index anomaly records by id for O(1) lookup
    anomaly_index: dict[str, AnomalyRecord] = {
        str(r["anomaly_id"]): r for r in anomaly_report  # type: ignore[literal-required]
    }

    changes: list[dict[str, Any]] = []
    resolved_ids: set[str] = set()

    for decision in user_decisions:
        aid = str(decision.get("anomaly_id", ""))
        action = str(decision.get("action", "keep_as_is"))
        params: dict[str, Any] = decision.get("params") or {}

        anomaly = anomaly_index.get(aid)
        if anomaly is None:
            logger.warning("Decision references unknown anomaly_id %s — skipping", aid)
            continue

        df, description = _apply_decision(df, anomaly, action, params)
        changes.append({"anomaly_id": aid, "action": action, "description": description})

        if action not in ("keep_as_is", "keep_all"):
            resolved_ids.add(aid)

        await auditor.log(
            agent_name="janitor", phase="phase2",
            action=description[:255],
            reason=f"User selected '{action}' for {anomaly['anomaly_type']}",  # type: ignore[literal-required]
            column_affected=anomaly.get("column_name"),  # type: ignore[arg-type]
            rows_affected=anomaly["affected_rows"],  # type: ignore[literal-required]
        )

    # Recalculate quality score on unresolved anomalies
    remaining = [r for r in anomaly_report if str(r["anomaly_id"]) not in resolved_ids]  # type: ignore[literal-required]
    quality_score_after = _compute_quality_score(remaining, len(df))

    # Save clean CSV
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    session_id = state["session_id"]  # type: ignore[literal-required]
    clean_path = processed_dir / f"{session_id}_clean.csv"
    df.to_csv(clean_path, index=False)

    logger.info(
        "Janitor: %d transformations applied, quality %.1f → %.1f, saved %s",
        len([c for c in changes if c["action"] not in ("keep_as_is", "keep_all")]),
        state.get("quality_score_before", 0.0),  # type: ignore[arg-type]
        quality_score_after,
        clean_path,
    )
    return {
        "df_clean": df,
        "clean_file_path": str(clean_path),
        "quality_score_after": quality_score_after,
        "changes_applied": changes,
    }


def _get_domain_floor(col: str) -> float:
    """
    Return the physical minimum value for a column based on its name.

    Columns matching SEMANTIC_NONNEG_DOMAIN_PATTERNS (age, revenue, price, …)
    can never be negative in the real world. Clamping IQR lower_fence to this
    floor prevents nonsensical caps like age ≥ -63.
    """
    col_lower = col.lower()
    if any(pat in col_lower for pat in SEMANTIC_NONNEG_DOMAIN_PATTERNS):
        return 0.0
    return float("-inf")


def _apply_decision(
    df: pd.DataFrame,
    anomaly: AnomalyRecord,
    action: str,
    params: dict[str, Any],
) -> tuple[pd.DataFrame, str]:
    """Apply one user decision; return (modified df, description string)."""
    df = df.copy()
    col: str | None = anomaly.get("column_name")  # type: ignore[assignment]
    atype: str = anomaly["anomaly_type"]  # type: ignore[literal-required]
    details: dict[str, Any] = anomaly.get("details") or {}  # type: ignore[assignment]

    if action in ("keep_as_is", "keep_all"):
        return df, f"Kept {atype} as-is (no change)"

    if action == "remove_duplicates":
        n = len(df)
        df = df.drop_duplicates(keep="first").reset_index(drop=True)
        return df, f"Removed {n - len(df)} duplicate rows"

    if action == "drop_column" and col and col in df.columns:
        df = df.drop(columns=[col])
        return df, f"Dropped column '{col}'"

    if action == "drop_rows":
        df, desc = _drop_rows(df, col, atype, details, params)
        return df, desc

    if action in ("fill_mean", "fill_median", "fill_mode") and col and col in df.columns:
        df, desc = _fill_missing(df, col, action, atype, details)
        return df, desc

    if action == "cap_iqr" and col and col in df.columns:
        lo, hi = details.get("lower_fence"), details.get("upper_fence")
        if lo is not None and hi is not None:
            lo = max(float(lo), _get_domain_floor(col))  # enforce physical minimum
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=lo, upper=hi)
            return df, f"Capped '{col}' to IQR fences [{lo:.4g}, {hi:.4g}]"

    if action == "clamp_bounds" and col and col in df.columns:
        lo = params.get("min_bound") or details.get("min_bound")
        hi = params.get("max_bound") or details.get("max_bound")
        if lo is not None and hi is not None:
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=lo, upper=hi)
            return df, f"Clamped '{col}' to [{lo}, {hi}]"

    if action == "treat_as_missing" and col and col in df.columns:
        num = pd.to_numeric(df[col], errors="coerce")
        if atype == "LOGICAL_VIOLATION":
            lo, hi = details.get("min_bound"), details.get("max_bound")
        else:  # STATISTICAL_OUTLIER
            lo, hi = details.get("lower_fence"), details.get("upper_fence")
        if lo is not None and hi is not None:
            mask = (num < lo) | (num > hi)
            df[col] = num.where(~mask, other=pd.NA)
            return df, (
                f"Set {int(mask.sum())} out-of-bounds value(s) in '{col}' "
                f"to missing (NaN) instead of clamping"
            )

    if action == "redact" and col and col in df.columns:
        df[col] = "[REDACTED]"
        return df, f"Redacted column '{col}'"

    if action == "hash_sha256" and col and col in df.columns:
        df[col] = df[col].astype(str).apply(
            lambda x: hashlib.sha256(x.encode()).hexdigest()
        )
        return df, f"SHA-256 hashed column '{col}'"

    logger.warning("Unhandled action '%s' for %s col=%s — skipping", action, atype, col)
    return df, f"Skipped unrecognised action '{action}'"


def _drop_rows(
    df: pd.DataFrame,
    col: str | None,
    atype: str,
    details: dict[str, Any],
    params: dict[str, Any],
) -> tuple[pd.DataFrame, str]:
    """Dispatch row-drop logic by anomaly type."""
    n = len(df)
    if atype == "MISSING_DATA" and col and col in df.columns:
        mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        df = df[~mask].reset_index(drop=True)
        return df, f"Dropped {n - len(df)} rows with missing '{col}'"

    if atype == "STATISTICAL_OUTLIER" and col and col in df.columns:
        lo, hi = details.get("lower_fence"), details.get("upper_fence")
        num = pd.to_numeric(df[col], errors="coerce")
        mask = (num < lo) | (num > hi)
        df = df[~mask].reset_index(drop=True)
        return df, f"Dropped {n - len(df)} outlier rows in '{col}'"

    if atype == "LOGICAL_VIOLATION" and col and col in df.columns:
        lo, hi = details.get("min_bound"), details.get("max_bound")
        num = pd.to_numeric(df[col], errors="coerce")
        mask = (num < lo) | (num > hi)
        df = df[~mask].reset_index(drop=True)
        return df, f"Dropped {n - len(df)} logically invalid rows in '{col}'"

    if atype == "ZERO_AS_MISSING" and col and col in df.columns:
        mask = pd.to_numeric(df[col], errors="coerce") == 0
        df = df[~mask].reset_index(drop=True)
        return df, f"Dropped {n - len(df)} zero-as-missing rows in '{col}'"

    if atype == "HIGH_NULL_DENSITY_ROWS":
        threshold = float(params.get("threshold", DEFAULT_NULL_DENSITY_ROW_THRESHOLD))
        mask = df.isnull().mean(axis=1) > threshold
        df = df[~mask].reset_index(drop=True)
        return df, f"Dropped {n - len(df)} high-null-density rows"

    return df, "drop_rows: no matching rule found — no change"


def _fill_missing(
    df: pd.DataFrame,
    col: str,
    action: str,
    atype: str,
    details: dict[str, Any],
) -> tuple[pd.DataFrame, str]:
    """Fill missing or zero values; handles STATISTICAL_OUTLIER inlier mean."""
    df = df.copy()
    num = pd.to_numeric(df[col], errors="coerce")

    if atype == "STATISTICAL_OUTLIER" and action == "fill_mean":
        lo, hi = details.get("lower_fence"), details.get("upper_fence")
        inlier_mean = float(num[(num >= lo) & (num <= hi)].mean())
        mask = (num < lo) | (num > hi)
        df[col] = num.where(~mask, inlier_mean)
        return df, f"Replaced {int(mask.sum())} outliers in '{col}' with inlier mean ({inlier_mean:.4g})"

    if atype == "ZERO_AS_MISSING" and action == "fill_mean":
        safe_mean = float(num.replace(0, pd.NA).mean())
        df[col] = num.replace(0, safe_mean)
        return df, f"Replaced zeros in '{col}' with non-zero mean ({safe_mean:.4g})"

    if action == "fill_mean":
        val = float(num.mean())
        df[col] = num.fillna(val)
        return df, f"Filled '{col}' NaNs with mean ({val:.4g})"

    if action == "fill_median":
        val = float(num.median())
        df[col] = num.fillna(val)
        return df, f"Filled '{col}' NaNs with median ({val:.4g})"

    if action == "fill_mode":
        # Mode imputation is statistically inappropriate for continuous float
        # columns — it concentrates the distribution around a single value.
        # Override to median for any float column or high-cardinality numeric.
        is_continuous = (
            pd.api.types.is_float_dtype(df[col])
            or df[col].nunique() > JANITOR_CONTINUOUS_CARDINALITY_THRESHOLD
        )
        if is_continuous:
            val = float(num.median())
            df[col] = num.fillna(val)
            return df, (
                f"Filled '{col}' NaNs with median ({val:.4g}) "
                f"[mode overridden: continuous column]"
            )
        modes = df[col].mode()
        val = modes.iloc[0] if len(modes) > 0 else None
        df[col] = df[col].fillna(val)
        return df, f"Filled '{col}' NaNs with mode ({val})"

    return df, f"fill action '{action}' unhandled for '{col}'"
