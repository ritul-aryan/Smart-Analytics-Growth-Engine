"""
ai_engine/agents/orchestrator.py — Phase 1 driver (Steps 1, 2, 4, 5, 6).

Loads file → normalises headers (LLM + regex fallback) → calls profiler →
contextual zero engine → 5-tier anomaly detection → quality score → persist.
Bug 1: pd.to_numeric(errors='coerce') before every IQR/comparison op.
Bug 2: null_rate included in every MISSING_DATA anomaly record.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.profiler import run_profiler
from ai_engine.config import (
    CSV_ENCODING_FALLBACKS,
    DEFAULT_NULL_DENSITY_ROW_THRESHOLD, DEFAULT_OUTLIER_IQR_MULTIPLIER,
    METADATA_SUMMARY_MAX_CHARS, METADATA_SUMMARY_MAX_COLUMNS_LISTED,
    PII_REGEX_PATTERNS, PII_SAMPLE_SIZE,
    PII_SEVERITY, QUALITY_PENALTY_CAPS, QUALITY_PENALTY_WEIGHTS,
    ROW_LIMIT_SOFT_WARNING, SEMANTIC_ZERO_ALWAYS_VALID_PATTERNS,
    SEVERITY_HIGH_THRESHOLD, SEVERITY_MEDIUM_THRESHOLD,
    ZERO_MEANINGFUL_KEYWORDS,
)
from ai_engine.graph.state import AnomalyRecord, GraphState
from ai_engine.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class _HeaderRenames(BaseModel):
    """LLM response schema for Step 2 header normalisation."""
    renames: dict[str, str]


async def run_phase1(
    state: GraphState,
    *,
    llm: LLMProvider,
    auditor: Auditor,
    iqr_multiplier: float = DEFAULT_OUTLIER_IQR_MULTIPLIER,
    null_density_threshold: float = DEFAULT_NULL_DENSITY_ROW_THRESHOLD,
) -> dict[str, Any]:
    """
    Execute Phase 1 pipeline; return partial GraphState dict or {'error': str}.

    Does not persist anomaly_report to the database itself -- the caller
    (backend/api/analyze.py) does that after this function returns, using
    the anomaly_report already present in the return dict. This keeps
    ai_engine free of backend.db.models imports (2026-07-03 architecture
    audit, decision log item 7).
    """
    try:
        # Allow user-configurable thresholds injected via state (Section 8.3)
        iqr_multiplier = float(state.get("outlier_iqr_multiplier", iqr_multiplier))  # type: ignore[call-overload]
        null_density_threshold = float(state.get("null_density_threshold", null_density_threshold))  # type: ignore[call-overload]
        if state.get("df_working") is not None:  # type: ignore[attr-defined]
            df_raw = state["df_working"]  # type: ignore[literal-required]
        else:
            df_raw, row_warning = _load_file(state["file_path"])  # type: ignore[literal-required]
            if row_warning:
                logger.warning("Dataset has %d rows — exceeds soft limit of %d", len(df_raw), ROW_LIMIT_SOFT_WARNING)
        df = df_raw.copy()
        renames = await _normalise_headers(df.columns.tolist(), state.get("user_intent") or "", llm)  # type: ignore[arg-type]
        df = df.rename(columns=renames)

        profile_result = await run_profiler({**state, "df_working": df}, llm=llm, auditor=auditor)
        domain_profile: dict[str, Any] = profile_result.get("domain_profile", {})

        zero_analysis = _contextual_zero_engine(df, domain_profile)
        anomaly_report = _run_anomaly_detection(
            df, zero_analysis, domain_profile, iqr_multiplier, null_density_threshold
        )
        quality_score = _compute_quality_score(anomaly_report, len(df))

        await auditor.update_session_status("audit", quality_score_before=quality_score)
        await auditor.log(
            agent_name="orchestrator", phase="phase1",
            action=f"Phase 1 complete — {len(anomaly_report)} anomalies, score {quality_score:.1f}",
            reason="Completed 5-tier anomaly detection pipeline",
            rows_affected=sum(a["affected_rows"] for a in anomaly_report),  # type: ignore[literal-required]
        )
        return {"df_raw": df_raw, "df_working": df, "column_renames": renames,
                "domain_profile": domain_profile, "zero_analysis": zero_analysis,
                "anomaly_report": anomaly_report, "quality_score_before": quality_score,
                "metadata_summary": _build_metadata_summary(df, anomaly_report, state["user_intent"])}
    except Exception as exc:
        logger.error("Orchestrator Phase 1 failed: %s", exc, exc_info=True)
        await auditor.update_session_status("error", error_message=str(exc))
        return {"error": str(exc)}


def _load_file(path: str) -> tuple[pd.DataFrame, bool]:
    """Load CSV or Excel; return (df, row_warning).

    For CSV files, tries each encoding in CSV_ENCODING_FALLBACKS in order so
    that real-world files encoded in latin-1 or cp1252 (common in Kaggle and
    government datasets) are handled without a UnicodeDecodeError crash.
    """
    if path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, engine="openpyxl")
    else:
        df = None
        for encoding in CSV_ENCODING_FALLBACKS:
            try:
                df = pd.read_csv(path, encoding=encoding, low_memory=False)
                logger.debug("Read CSV with encoding=%s: %s", encoding, path)
                break
            except UnicodeDecodeError:
                logger.debug("Encoding %s failed for %s, trying next", encoding, path)
        if df is None:
            raise ValueError(
                f"Could not decode {path} with any of: {CSV_ENCODING_FALLBACKS}"
            )
    logger.info("Loaded %d x %d from %s", len(df), len(df.columns), path)
    return df, len(df) > ROW_LIMIT_SOFT_WARNING


async def _normalise_headers(columns: list[str], intent: str, llm: LLMProvider) -> dict[str, str]:
    """LLM snake_case rename with regex fallback."""
    prompt = (f"Rename to snake_case. Context: {intent or 'unknown'}. Columns: {columns}\n"
              'Return JSON: {"renames": {"Original": "snake_case", ...}}')
    try:
        resp = await llm.complete_json(prompt, _HeaderRenames, task="normalisation")
        renames = {k: v for k, v in resp.renames.items() if k in columns}
        for col in columns:
            if col not in renames:
                renames[col] = _regex_normalise(col)
        return renames
    except Exception as exc:
        logger.warning("LLM header normalisation failed (%s) — regex fallback", exc)
        return {col: _regex_normalise(col) for col in columns}


def _regex_normalise(name: str) -> str:
    """Convert a column name to snake_case without an LLM."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())).strip("_") or "column"


def _contextual_zero_engine(df: pd.DataFrame, domain_profile: dict[str, Any]) -> dict[str, str]:
    """
    Classify zeros per numeric column as ABSOLUTE_ZERO, MISSING_ZERO, or BOUNDARY_ZERO.

    Priority order (first match wins):
      1. SEMANTIC_ZERO_ALWAYS_VALID_PATTERNS — revenue/price/etc zeros are always valid
      2. Boolean {0, 1} columns — zeros are a legitimate flag value
      3. ZERO_MEANINGFUL_KEYWORDS — domain keywords marking zero as meaningful
      4. LLM domain profile min_bound > 0 — LLM said column must be strictly positive
      5. Heuristic — all non-zero values positive → zeros likely missing
    """
    result: dict[str, str] = {}
    for col in df.select_dtypes(include="number").columns:
        col_lower = col.lower()

        # 1. Business-critical zero columns — never flag as missing
        if any(kw in col_lower for kw in SEMANTIC_ZERO_ALWAYS_VALID_PATTERNS):
            result[col] = "ABSOLUTE_ZERO"
            continue

        # 2. Boolean flag columns — {0, 1} only; zero is a valid flag state
        unique_vals = set(df[col].dropna().unique())
        if unique_vals <= {0, 1, True, False}:
            result[col] = "ABSOLUTE_ZERO"
            continue

        # 3. General domain keywords (e.g. "count", "quantity")
        if any(kw in col_lower for kw in ZERO_MEANINGFUL_KEYWORDS):
            result[col] = "ABSOLUTE_ZERO"
            continue

        # 4. LLM domain profile says min_bound is strictly positive
        if domain_profile.get(col, {}).get("min_bound", -1) > 0:
            result[col] = "MISSING_ZERO"
            continue

        # 5. Heuristic: all non-zero values strictly positive → zeros likely missing
        non_zero = pd.to_numeric(df[col], errors="coerce").replace(0, pd.NA).dropna()
        if len(non_zero) > 0 and (non_zero > 0).all():
            result[col] = "MISSING_ZERO"
        else:
            result[col] = "BOUNDARY_ZERO"

    return result


def _rec(atype: str, n: int, total: int, col: str | None, null_rate: float | None,
         details: dict[str, Any], total_flagged: int | None = None) -> dict[str, Any]:
    """Construct a standard anomaly record dict.

    n             -> affected_rows: priority-chain attribution count (rows uniquely
                     attributed to THIS anomaly; drives quality score + severity).
    total_flagged -> true per-column count of matching values before priority-chain
                     de-duplication; shown on the review card so the number matches
                     what will actually change. Defaults to n when not supplied.
    """
    d = dict(details)
    d["total_flagged"] = n if total_flagged is None else total_flagged
    return {"anomaly_id": str(uuid4()), "anomaly_type": atype, "column_name": col,
            "affected_rows": n, "null_rate": null_rate, "severity": _severity(n, total),
            "details": d, "user_action": None, "action_params": None, "resolved_at": None}


def _run_anomaly_detection(
    df: pd.DataFrame, zero_analysis: dict[str, str], domain_profile: dict[str, Any],
    iqr_mult: float, null_density_thresh: float,
) -> list[AnomalyRecord]:
    """Drive the 5-tier priority chain; returns ordered AnomalyRecord list."""
    c = pd.Series(False, index=df.index)
    recs: list[Any] = []

    def _add(rs: list[dict[str, Any]], m: pd.Series, *, supp: bool = False) -> None:
        """Append records with display_order; update claimed mask unless supplementary."""
        nonlocal c
        for r in rs: r["display_order"] = len(recs); recs.append(r)
        if not supp: c = c | m

    _add(*_t1_duplicates(df, c))
    _add(*_t2_missing(df, c))
    _add(*_t3_zero_missing(df, zero_analysis, c))
    _add(*_t4_logical(df, domain_profile, c))
    _add(*_t5_outliers(df, iqr_mult, c))
    _add(*_s_pii(df), supp=True)
    _add(*_s_null_density(df, null_density_thresh), supp=True)
    return recs  # type: ignore[return-value]


def _t1_duplicates(df: pd.DataFrame, c: pd.Series) -> tuple[list[dict[str, Any]], pd.Series]:
    """Priority 1 — exact duplicate rows."""
    m = df.duplicated(keep="first") & ~c
    if not m.any():
        return [], _false(df)
    return [_rec("DUPLICATE_ROWS", int(m.sum()), len(df), None, None, {"sample_indices": df.index[m].tolist()[:5]})], m


def _t2_missing(df: pd.DataFrame, c: pd.Series) -> tuple[list[dict[str, Any]], pd.Series]:
    """Priority 2 — NaN/empty per column. Includes null_rate (Bug 2 fix)."""
    recs, combined = [], _false(df)
    for col in df.columns:
        m_all = df[col].isna() | (df[col].astype(str).str.strip() == "")
        m = m_all & ~c
        if m.any():
            nr = float(df[col].isna().mean())
            recs.append(_rec("MISSING_DATA", int(m.sum()), len(df), col, nr,
                             {"null_rate": nr}, total_flagged=int(m_all.sum())))
            combined = combined | m
    return recs, combined


def _t3_zero_missing(df: pd.DataFrame, zero_analysis: dict[str, str], c: pd.Series) -> tuple[list[dict[str, Any]], pd.Series]:
    """Priority 3 — MISSING_ZERO classified zeros."""
    recs, combined = [], _false(df)
    for col, ztype in zero_analysis.items():
        if ztype != "MISSING_ZERO" or col not in df.columns:
            continue
        num_zero = (pd.to_numeric(df[col], errors="coerce") == 0)
        m = num_zero & ~c
        if m.any():
            recs.append(_rec("ZERO_AS_MISSING", int(m.sum()), len(df), col, None,
                             {"zero_count": int(m.sum())}, total_flagged=int(num_zero.sum())))
            combined = combined | m
    return recs, combined


def _t4_logical(df: pd.DataFrame, domain_profile: dict[str, Any], c: pd.Series) -> tuple[list[dict[str, Any]], pd.Series]:
    """Priority 4 — values outside LLM semantic bounds. Bug 1: cast to numeric."""
    recs, combined = [], _false(df)
    for col, bounds in domain_profile.items():
        if col not in df.columns:
            continue
        num = pd.to_numeric(df[col], errors="coerce")
        lo, hi = bounds.get("min_bound"), bounds.get("max_bound")
        if lo is None or hi is None:
            continue
        m_all = ((num < lo) | (num > hi)) & num.notna()
        m = m_all & ~c
        if m.any():
            recs.append(_rec("LOGICAL_VIOLATION", int(m.sum()), len(df), col, None,
                             {"min_bound": lo, "max_bound": hi, "description": bounds.get("description", "")},
                             total_flagged=int(m_all.sum())))
            combined = combined | m
    return recs, combined


def _t5_outliers(df: pd.DataFrame, iqr_mult: float, c: pd.Series) -> tuple[list[dict[str, Any]], pd.Series]:
    """Priority 5 — statistical outliers. Bug 1: cast to numeric."""
    recs, combined = [], _false(df)
    for col in df.select_dtypes(include="number").columns:
        num = pd.to_numeric(df[col], errors="coerce")
        q1, q3 = num.quantile(0.25), num.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            # Fallback: MAD-based detection when all values are identical except outliers
            med = num.median()
            mad = (num - med).abs().median()
            if mad == 0:
                continue
            fence = iqr_mult * mad * 1.4826
            m_all = ((num - med).abs() > fence) & num.notna()
            lo, hi = float(med - fence), float(med + fence)
        else:
            lo, hi = float(q1 - iqr_mult * iqr), float(q3 + iqr_mult * iqr)
            m_all = ((num < lo) | (num > hi)) & num.notna()
        m = m_all & ~c
        if m.any():
            recs.append(_rec("STATISTICAL_OUTLIER", int(m.sum()), len(df), col, None,
                             {"lower_fence": lo, "upper_fence": hi}, total_flagged=int(m_all.sum())))
            combined = combined | m
    return recs, combined


def _s_pii(df: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.Series]:
    """Supplementary — regex PII detection. Not in claimed chain."""
    recs = []
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna().head(PII_SAMPLE_SIZE).astype(str)
        found = [t for t, p in PII_REGEX_PATTERNS.items() if sample.str.contains(p, na=False, regex=True).any()]
        if found:
            r = _rec("PII_DETECTED", len(df), len(df), col, None, {"pii_types_found": found})
            r["severity"] = PII_SEVERITY
            recs.append(r)
    return recs, _false(df)


def _s_null_density(df: pd.DataFrame, threshold: float) -> tuple[list[dict[str, Any]], pd.Series]:
    """Supplementary — rows with > threshold fraction of null columns."""
    m = df.isnull().mean(axis=1) > threshold
    if not m.any():
        return [], _false(df)
    return [_rec("HIGH_NULL_DENSITY_ROWS", int(m.sum()), len(df), None, None,
                 {"threshold": threshold, "mean_null_density": float(df.isnull().mean(axis=1)[m].mean())})], _false(df)


def _false(df: pd.DataFrame) -> pd.Series:
    """All-False boolean Series matching df's index."""
    return pd.Series(False, index=df.index)


def _severity(affected: int, total: int) -> str:
    """Return 'high', 'medium', or 'low' from affected-row fraction."""
    r = affected / max(total, 1)
    return "high" if r >= SEVERITY_HIGH_THRESHOLD else ("medium" if r >= SEVERITY_MEDIUM_THRESHOLD else "low")


def _compute_quality_score(anomaly_report: list[AnomalyRecord], total_rows: int) -> float:
    """0–100 quality score using per-type weighted penalties with caps."""
    if total_rows == 0:
        return 100.0
    penalty = sum(
        min(QUALITY_PENALTY_WEIGHTS.get(r["anomaly_type"], 0.0) * r["affected_rows"] / total_rows * 100,  # type: ignore[literal-required]
            QUALITY_PENALTY_CAPS.get(r["anomaly_type"], 10.0))  # type: ignore[literal-required]
        for r in anomaly_report
    )
    return max(0.0, round(100.0 - penalty, 2))


def _build_metadata_summary(df: pd.DataFrame, anomaly_report: list[AnomalyRecord], intent: str) -> str:
    """Compact context string passed to LLM calls in later pipeline phases."""
    s = (f"Rows:{len(df)} Cols:{len(df.columns)} | Intent:{intent or 'N/A'} | "
         f"Anomalies:{len(anomaly_report)} ({','.join(set(a['anomaly_type'] for a in anomaly_report))}) | "  # type: ignore[literal-required]
         f"Numeric:{list(df.select_dtypes(include='number').columns[:METADATA_SUMMARY_MAX_COLUMNS_LISTED])} | "
         f"Categorical:{list(df.select_dtypes(include='object').columns[:METADATA_SUMMARY_MAX_COLUMNS_LISTED])}")
    return s[:METADATA_SUMMARY_MAX_CHARS]
