"""
ai_engine/agents/engineer.py -- Phase 2.5 feature-engineering agent.

Six deterministic transforms; LLMs are NOT used here.

  1. OHE           -- object/category cols with 2-DEFAULT_OHE_MAX_UNIQUE unique values.
                      Originals KEPT; OHE columns APPENDED alongside (drop_first=False).
  2. Frequency enc -- high-cardinality fallback: object/category cols with
                      ohe_max_unique+1 .. DEFAULT_FREQ_ENCODING_MAX_UNIQUE uniques
                      get a `<col>_freq` column (occurrence count per category).
                      Beyond that bound the column is skipped entirely.
  3. Log transform  -- numeric cols: skew > LOG_SKEW_THRESHOLD, no negatives,
                       nunique >= ENGINEER_MIN_UNIQUE_FOR_TRANSFORM, not ID/BOOLEAN.
  4. Datetime extr  -- native datetime dtype, semantic TIMESTAMP cols (name match
                       + Unix-second value range), OR object cols with time-like
                       names parsing at >= DATETIME_PARSE_MIN_SUCCESS_RATE.
                       Extracts year / month / dow / is_weekend.
  5. Duration       -- when 2+ datetime columns qualify, a duration-in-days
                       column between the first two (in column order).
  6. Interaction    -- product of highest-correlated pair |r| > ENGINEER_INTERACTION_MIN_R,
                       excludes ID and BOOLEAN columns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from ai_engine.agents.auditor import Auditor
from ai_engine.config import (
    DATETIME_PARSE_MIN_SUCCESS_RATE,
    DEFAULT_FREQ_ENCODING_MAX_UNIQUE,
    DEFAULT_OHE_MAX_UNIQUE,
    ENGINEER_INTERACTION_MIN_R,
    ENGINEER_LOG_SKEW_THRESHOLD,
    ENGINEER_MIN_UNIQUE_FOR_TRANSFORM,
    SEMANTIC_ID_CARDINALITY_THRESHOLD,
    SEMANTIC_ID_NAME_PATTERNS,
    SEMANTIC_TIMESTAMP_NAME_PATTERNS,
    SEMANTIC_UNIX_TS_MAX,
    SEMANTIC_UNIX_TS_MIN,
)
from ai_engine.graph.state import FeatureRecord, GraphState

logger = logging.getLogger(__name__)

SemanticType = Literal["ID", "BOOLEAN", "TIMESTAMP", "CONTINUOUS"]

# Fallback output directory, used only when a caller does not supply its own.
# Mirrors the LOCAL_PROCESSED_DIR default in .env.example (Section 11.5).
# Production callers (backend/api/analyze.py) resolve the real configured
# path from backend.config.Settings.processed_dir and pass it in explicitly
# -- ai_engine does not import backend directly (2026-07-03 architecture
# audit, decision log item 7).
_DEFAULT_PROCESSED_DIR = Path("./data/processed")


# ---------------------------------------------------------------------------
# Semantic type inference
# ---------------------------------------------------------------------------

def _infer_semantic_type(df: pd.DataFrame, col: str) -> SemanticType:
    """
    Classify a numeric column into one of four semantic types.

    BOOLEAN   -- unique values subset of {0, 1}; skip log/interaction.
    ID        -- cardinality >= SEMANTIC_ID_CARDINALITY_THRESHOLD AND name contains
                 an ID-like substring; skip all transforms.
    TIMESTAMP -- name contains a time-like substring AND values fall in the
                 Unix-second range; both conditions required.
    CONTINUOUS -- everything else; eligible for all transforms.
    """
    series = df[col]
    col_lower = col.lower()

    unique_vals = set(series.dropna().unique())
    if unique_vals <= {0, 1, True, False}:
        return "BOOLEAN"

    n_rows = len(series)
    if n_rows > 0:
        cardinality_ratio = series.nunique() / n_rows
        name_looks_like_id = any(pat in col_lower for pat in SEMANTIC_ID_NAME_PATTERNS)
        if cardinality_ratio >= SEMANTIC_ID_CARDINALITY_THRESHOLD and name_looks_like_id:
            return "ID"

    if pd.api.types.is_numeric_dtype(series):
        name_looks_like_ts = any(pat in col_lower for pat in SEMANTIC_TIMESTAMP_NAME_PATTERNS)
        if name_looks_like_ts:
            non_null = series.dropna()
            if len(non_null) > 0:
                col_min = float(non_null.min())
                col_max = float(non_null.max())
                if SEMANTIC_UNIX_TS_MIN <= col_min and col_max <= SEMANTIC_UNIX_TS_MAX:
                    return "TIMESTAMP"

    return "CONTINUOUS"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_engineer(
    state: GraphState,
    *,
    auditor: Auditor,
    processed_dir: Path | str = _DEFAULT_PROCESSED_DIR,
) -> dict[str, Any]:
    """
    Apply feature-engineering transforms; return df_engineered, engineered_file_path, fe_report.

    processed_dir: directory to save the engineered CSV into. Callers resolve
    this from their own config (e.g. backend.config.Settings.processed_dir).
    """
    df: pd.DataFrame = state["df_clean"].copy()  # type: ignore[index]
    session_id: str = state["session_id"]  # type: ignore[literal-required]

    # Read user-configurable thresholds from state; fall back to config defaults.
    # Explicit int()/float() casts guard against string values sent from the
    # frontend form (FormData always serialises to str) — without the cast,
    # `nunique <= "15"` would silently evaluate as False and skip all OHE work.
    ohe_max_unique     = int(float(state.get("ohe_max_unique",     DEFAULT_OHE_MAX_UNIQUE)))  # type: ignore[call-overload]
    log_skew_threshold = float(state.get("log_skew_threshold",    ENGINEER_LOG_SKEW_THRESHOLD))  # type: ignore[call-overload]
    interaction_min_r  = float(state.get("correlation_threshold", ENGINEER_INTERACTION_MIN_R))  # type: ignore[call-overload]

    fe_report: list[FeatureRecord] = []

    df, ohe_records, ohe_skipped = _apply_ohe(df, ohe_max_unique=ohe_max_unique)
    fe_report.extend(ohe_records)

    # High-cardinality fallback: columns above the OHE cap but within the
    # frequency-encoding bound get a `<col>_freq` occurrence-count column.
    df, freq_records = _apply_frequency_encoding(
        df,
        min_unique=ohe_max_unique + 1,
        max_unique=DEFAULT_FREQ_ENCODING_MAX_UNIQUE,
    )
    fe_report.extend(freq_records)
    freq_encoded = {rec["source_columns"][0] for rec in freq_records}

    df, log_records = _apply_log_transform(df, log_skew_threshold=log_skew_threshold)
    fe_report.extend(log_records)

    df, dt_records = _apply_datetime_extraction(df)
    fe_report.extend(dt_records)
    datetime_handled = {
        rec["source_columns"][0]
        for rec in dt_records
        if rec["transform_type"] == "DATETIME_EXTRACTION"
    }

    # Audit every high-cardinality column that was bypassed ENTIRELY so the
    # FE Report tab gives a clear paper trail ("why is my column untouched?").
    # Columns that received frequency encoding or datetime extraction are
    # already logged via their fe_report records below.
    for col in ohe_skipped:
        if col in freq_encoded or col in datetime_handled:
            continue
        n_unique = int(df[col].nunique())
        await auditor.log(
            agent_name="engineer", phase="phase2",
            action=(
                f"Skipped encoding for '{col}' (cardinality={n_unique} > "
                f"frequency-encoding max={DEFAULT_FREQ_ENCODING_MAX_UNIQUE})"
            ),
            reason="SKIPPED_OHE",
            column_affected=col,
            rows_affected=0,
        )
        logger.info(
            "Engineer: skipped encoding for '%s' (nunique=%d > freq max=%d)",
            col, n_unique, DEFAULT_FREQ_ENCODING_MAX_UNIQUE,
        )

    df, int_records = _apply_interaction_term(df, interaction_min_r=interaction_min_r)
    fe_report.extend(int_records)

    for rec in fe_report:
        await auditor.log(
            agent_name="engineer", phase="phase2",
            action=rec["description"],  # type: ignore[literal-required]
            reason=rec["transform_type"],  # type: ignore[literal-required]
            column_affected=rec.get("source_columns", [""])[0],  # type: ignore[arg-type]
            rows_affected=len(df),
        )

    # Fallback: always emit at least one audit entry so the FE Report tab is
    # never blank.  A silent agent looks broken — this makes the no-op visible.
    if not fe_report:
        await auditor.log(
            agent_name="engineer", phase="phase2",
            action=(
                f"No feature engineering applied — data did not meet thresholds "
                f"(OHE max_unique={ohe_max_unique}, log skew>{log_skew_threshold:.2f}, "
                f"interaction |r|>{interaction_min_r:.2f})"
            ),
            reason="NO_TRANSFORMS",
            column_affected="N/A",
            rows_affected=len(df),
        )
        logger.info(
            "Engineer: no transforms applied (ohe_max_unique=%d, log_skew=%.2f, min_r=%.2f)",
            ohe_max_unique, log_skew_threshold, interaction_min_r,
        )

    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    eng_path = processed_dir / f"{session_id}_engineered.csv"
    df.to_csv(eng_path, index=False)

    logger.info("Engineer: %d features added, saved %s", len(fe_report), eng_path)
    return {
        "df_engineered": df,
        "engineered_file_path": str(eng_path),
        "fe_report": fe_report,
    }


# ---------------------------------------------------------------------------
# OHE -- originals kept; OHE columns appended alongside
#
# Deliberate, documented deviation from spec Section 6.2, which specifies
# "pd.get_dummies(drop_first=True)". Kept as drop_first=False + original
# column preserved because: (1) Section 6.2 also requires the correlation
# heatmap to show every category, which drop_first=True would break for the
# dropped reference category; (2) the original text column stays in the
# human-readable clean/engineered CSV export; (3) Section 3.1's roadmap
# marks "Data Modeling & Advanced Analysis" as PARTIAL / "ML modeling
# planned" -- the classic reason to prefer drop_first=True (avoiding the
# dummy-variable trap for linear regression) does not yet apply since no
# model-fitting step consumes these columns. Revisit drop_first=True if/when
# real model training is added (2026-07-04 architecture audit follow-up,
# decision log item 13 -- flagged to and accepted by the user rather than
# silently kept or silently reverted).
# ---------------------------------------------------------------------------

def _apply_ohe(
    df: pd.DataFrame,
    *,
    ohe_max_unique: int = DEFAULT_OHE_MAX_UNIQUE,
) -> tuple[pd.DataFrame, list[FeatureRecord], list[str]]:
    """
    One-hot encode object/category columns with 2-ohe_max_unique uniques.

    Original text column is PRESERVED (human-readable CSV export).
    New binary OHE columns are APPENDED alongside the original.
    drop_first=False so all categories appear in the correlation matrix.
    dtype=int so downstream numeric transforms see integer columns.

    NOTE: spec Section 6.2 literally says "drop_first=True" -- this function
    intentionally does not follow that; see the module-level comment above
    this function for the accepted rationale (decision log item 13).

    Returns (df, records, skipped) where skipped is the list of column names
    that were bypassed because nunique > ohe_max_unique.  The caller
    (run_engineer) logs each skip to the audit trail.
    """
    df = df.copy()
    records: list[FeatureRecord] = []
    skipped: list[str] = []

    cat_cols = df.select_dtypes(include=["object", "category"]).columns
    for c in cat_cols:
        n = int(df[c].nunique())
        if n > ohe_max_unique:
            skipped.append(c)

    candidates = [c for c in cat_cols if 2 <= df[c].nunique() <= ohe_max_unique]
    if not candidates and not skipped:
        return df, records, skipped

    for col in candidates:
        dummies = pd.get_dummies(df[col], prefix=col, drop_first=False, dtype=int)
        new_cols = list(dummies.columns)
        df = pd.concat([df, dummies[new_cols]], axis=1)
        records.append({
            "transform_type": "OHE",
            "source_columns": [col],
            "output_columns": new_cols,
            "description": (
                f"One-hot encoded '{col}' -> {new_cols} "
                f"(original column kept, drop_first=False)"
            ),
        })

    return df, records, skipped


# ---------------------------------------------------------------------------
# Frequency encoding -- high-cardinality fallback for skipped OHE columns
# ---------------------------------------------------------------------------

def _apply_frequency_encoding(
    df: pd.DataFrame,
    *,
    min_unique: int,
    max_unique: int = DEFAULT_FREQ_ENCODING_MAX_UNIQUE,
) -> tuple[pd.DataFrame, list[FeatureRecord]]:
    """
    Frequency-encode object/category columns with min_unique..max_unique uniques.

    Each category value is mapped to its occurrence count in the column,
    written to a new `<col>_freq` column (nullable Int64 so NaN survives).
    The original column is PRESERVED, mirroring the OHE philosophy.

    Called with min_unique = ohe_max_unique + 1, so it picks up exactly the
    columns the OHE pass bypassed, up to the frequency-encoding bound.
    """
    df = df.copy()
    records: list[FeatureRecord] = []

    cat_cols = df.select_dtypes(include=["object", "category"]).columns
    for col in cat_cols:
        n = int(df[col].nunique())
        if not (min_unique <= n <= max_unique):
            continue
        counts = df[col].value_counts(dropna=True)
        new_col = f"{col}_freq"
        df[new_col] = df[col].map(counts).astype("Int64")
        records.append({
            "transform_type": "FREQUENCY_ENCODING",
            "source_columns": [col],
            "output_columns": [new_col],
            "description": (
                f"Frequency-encoded '{col}' -> '{new_col}' "
                f"(cardinality={n} exceeds OHE cap; each category replaced by "
                f"its occurrence count; original column kept)"
            ),
        })
        logger.info(
            "Engineer: frequency-encoded '%s' -> '%s' (nunique=%d)",
            col, new_col, n,
        )

    return df, records


# ---------------------------------------------------------------------------
# Log transform -- skips ID and BOOLEAN columns
# ---------------------------------------------------------------------------

def _apply_log_transform(
    df: pd.DataFrame,
    *,
    log_skew_threshold: float = ENGINEER_LOG_SKEW_THRESHOLD,
) -> tuple[pd.DataFrame, list[FeatureRecord]]:
    """Add log1p column for skewed positive numeric columns (ID and BOOLEAN excluded)."""
    df = df.copy()
    records: list[FeatureRecord] = []

    num_cols = df.select_dtypes(include="number").columns.tolist()
    for col in num_cols:
        if _infer_semantic_type(df, col) in ("ID", "BOOLEAN"):
            continue

        series = pd.to_numeric(df[col], errors="coerce")
        non_null = series.dropna()
        if len(non_null) == 0:
            continue
        skew = float(series.skew())
        if (
            series.nunique() >= ENGINEER_MIN_UNIQUE_FOR_TRANSFORM
            and float(non_null.min()) >= 0.0
            and abs(skew) > log_skew_threshold
        ):
            new_col = f"{col}_log"
            df[new_col] = np.log1p(series)
            records.append({
                "transform_type": "LOG_TRANSFORM",
                "source_columns": [col],
                "output_columns": [new_col],
                "description": f"log1p('{col}') -> '{new_col}' (skew={skew:.2f})",
            })
    return df, records


# ---------------------------------------------------------------------------
# Datetime extraction -- native datetime OR semantic TIMESTAMP only
# ---------------------------------------------------------------------------

def _detect_datetime_series(df: pd.DataFrame, col: str) -> "pd.Series | None":
    """
    Return the column parsed as datetime, or None if it does not qualify.

    Qualifies if:
      (a) dtype is already datetime64, OR
      (b) numeric AND semantic type is TIMESTAMP (Unix-second range + time-like name), OR
      (c) object dtype AND name is time-like AND at least
          DATETIME_PARSE_MIN_SUCCESS_RATE of non-null values parse as dates.

    Plain integers or arbitrary strings without time-like names are never
    coerced -- no more 1970 features (prototype bug).
    """
    series = df[col]
    dtype_str = str(series.dtype)

    if dtype_str.startswith("datetime"):
        return series

    if pd.api.types.is_numeric_dtype(series):
        if _infer_semantic_type(df, col) != "TIMESTAMP":
            return None
        dt = pd.to_datetime(series, unit="s", errors="coerce")
        # Was hardcoded 0.5, inconsistent with the object-column branch below
        # which uses DATETIME_PARSE_MIN_SUCCESS_RATE (0.80) for what is
        # conceptually the same "does this look like a real datetime column"
        # check (2026-07-03 architecture audit, config threshold review).
        return dt if dt.notna().mean() >= DATETIME_PARSE_MIN_SUCCESS_RATE else None

    if dtype_str in ("object", "category"):
        name_looks_like_ts = any(
            pat in col.lower() for pat in SEMANTIC_TIMESTAMP_NAME_PATTERNS
        )
        if not name_looks_like_ts:
            return None
        non_null = series.dropna()
        if len(non_null) == 0:
            return None
        dt = pd.to_datetime(series, errors="coerce", format="mixed")
        success_rate = float(dt.notna().sum()) / float(len(non_null))
        return dt if success_rate >= DATETIME_PARSE_MIN_SUCCESS_RATE else None

    return None


def _apply_datetime_extraction(df: pd.DataFrame) -> tuple[pd.DataFrame, list[FeatureRecord]]:
    """
    Extract year, month, day-of-week, is_weekend from every qualifying
    datetime column (see _detect_datetime_series for the detection rules).

    When two or more datetime columns qualify, additionally computes a
    duration-in-days column between the FIRST TWO (in column order):
    `duration_days_<colA>_to_<colB>` = (colB - colA).dt.days.
    """
    df = df.copy()
    records: list[FeatureRecord] = []
    parsed: list[tuple[str, pd.Series]] = []

    for col in list(df.columns):
        dt = _detect_datetime_series(df, col)
        if dt is None:
            continue
        parsed.append((col, dt))

        yr_col  = f"{col}_year"
        mo_col  = f"{col}_month"
        dow_col = f"{col}_dow"
        we_col  = f"{col}_is_weekend"

        df[yr_col]  = dt.dt.year.astype("Int64")
        df[mo_col]  = dt.dt.month.astype("Int64")
        df[dow_col] = dt.dt.dayofweek.astype("Int64")
        df[we_col]  = (dt.dt.dayofweek >= 5).astype("Int64")

        records.append({
            "transform_type": "DATETIME_EXTRACTION",
            "source_columns": [col],
            "output_columns": [yr_col, mo_col, dow_col, we_col],
            "description": f"Extracted year/month/dow/is_weekend from '{col}'",
        })

    # Duration between the first two detected date columns (Sprint 5).
    if len(parsed) >= 2:
        (col_a, dt_a), (col_b, dt_b) = parsed[0], parsed[1]
        dur_col = f"duration_days_{col_a}_to_{col_b}"
        try:
            df[dur_col] = (dt_b - dt_a).dt.days.astype("Int64")
            records.append({
                "transform_type": "DURATION",
                "source_columns": [col_a, col_b],
                "output_columns": [dur_col],
                "description": (
                    f"Duration in days between '{col_a}' and '{col_b}' "
                    f"-> '{dur_col}' ('{col_b}' minus '{col_a}')"
                ),
            })
        except TypeError as exc:
            # Mixed tz-aware / tz-naive columns cannot be subtracted; skip
            # rather than fail the whole pipeline.
            logger.warning(
                "Engineer: duration between '%s' and '%s' skipped (%s)",
                col_a, col_b, exc,
            )

    return df, records


# ---------------------------------------------------------------------------
# Interaction term -- excludes ID and BOOLEAN columns
# ---------------------------------------------------------------------------

def _apply_interaction_term(
    df: pd.DataFrame,
    *,
    interaction_min_r: float = ENGINEER_INTERACTION_MIN_R,
) -> tuple[pd.DataFrame, list[FeatureRecord]]:
    """Create a product column for the highest-correlated numeric pair (ID/BOOLEAN excluded)."""
    df = df.copy()
    records: list[FeatureRecord] = []

    num_cols = [
        c for c in df.select_dtypes(include="number").columns
        if df[c].nunique() >= ENGINEER_MIN_UNIQUE_FOR_TRANSFORM
        and _infer_semantic_type(df, c) not in ("ID", "BOOLEAN")
    ]
    if len(num_cols) < 2:
        return df, records

    corr = df[num_cols].corr()
    corr_values = corr.to_numpy().copy()
    np.fill_diagonal(corr_values, 0.0)
    corr_values = np.abs(corr_values)

    best_val = float(corr_values.max())
    if best_val < interaction_min_r:
        return df, records

    row_idx, col_idx = np.unravel_index(corr_values.argmax(), corr_values.shape)
    col_a = num_cols[row_idx]
    col_b = num_cols[col_idx]
    new_col = f"{col_a}_x_{col_b}"

    df[new_col] = (
        pd.to_numeric(df[col_a], errors="coerce")
        * pd.to_numeric(df[col_b], errors="coerce")
    )
    records.append({
        "transform_type": "INTERACTION_TERM",
        "source_columns": [col_a, col_b],
        "output_columns": [new_col],
        "description": (
            f"Interaction '{col_a}' x '{col_b}' -> '{new_col}' (r={best_val:.2f})"
        ),
    })
    return df, records
