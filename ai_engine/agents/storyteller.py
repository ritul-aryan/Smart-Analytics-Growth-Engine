"""
ai_engine/agents/storyteller.py — Phase 3 EDA portfolio agent.

LLM use: ONLY for primary chart type + axis selection.
All statistics, narrative text, and chart configs are computed programmatically.

Portfolio: primary (LLM), histograms, box plots, correlation heatmap,
           scatter matrix, time-series, missingness heatmap.
Narrative: top-3 Spearman correlations, missingness hotspots,
           ML readiness score, intent-aligned recommendation.

NaN safety: all float values are sanitised via safe_float() and
sanitize_json() before JSON serialisation to prevent browser
JSON.parse() failures. Both are public (no leading underscore) since
backend/api/analyze.py imports sanitize_json() too, to sanitise
eda_narrative before persisting it -- chart/narrative persistence moved out
of this module (2026-07-03 architecture audit, decision log item 7).
"""

from __future__ import annotations

import json
import logging
import math
import uuid
import warnings
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy import stats as sp_stats  # type: ignore[import]

from ai_engine.agents.auditor import Auditor
from ai_engine.config import (
    DEFAULT_OUTLIER_IQR_MULTIPLIER,
    IMPUTATION_VARIANCE_WARN_THRESHOLD,
    SEMANTIC_ID_CARDINALITY_THRESHOLD,
    SEMANTIC_ID_NAME_PATTERNS,
    STORYTELLER_COLLINEARITY_THRESHOLD,
    STORYTELLER_CORR_FEATURE_CANDIDATE_THRESHOLD,
    STORYTELLER_CORR_MODERATE_THRESHOLD,
    STORYTELLER_CORR_STRONG_THRESHOLD,
    STORYTELLER_HEATMAP_MIN_CORR,
    STORYTELLER_MAX_CHART_ROWS,
    STORYTELLER_MAX_HISTO_COLS,
    STORYTELLER_NULL_PENALTY_NOTE_THRESHOLD,
    STORYTELLER_SCATTER_MAX_COLS,
    STORYTELLER_SCATTER_MIN_COLS,
    STORYTELLER_SKEW_DIRECTION_THRESHOLD,
    STORYTELLER_TREND_PCT_THRESHOLD,
)
from ai_engine.graph.state import ChartSpec, GraphState
from ai_engine.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class _PrimaryChartSelection(BaseModel):
    chart_type: str
    x_column: str | None = None
    y_column: str | None = None
    color_column: str | None = None
    title: str


# ---------------------------------------------------------------------------
# NaN / Inf sanitisation — must run on every value before json.dumps
# ---------------------------------------------------------------------------

def safe_float(v: Any) -> Any:
    """Return None for NaN/Inf floats; pass everything else through."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def sanitize_json(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None so json.dumps produces valid JSON."""
    if isinstance(obj, float):
        return safe_float(obj)
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Chart column guard
# ---------------------------------------------------------------------------

def _is_chart_safe(df: pd.DataFrame, col: str) -> bool:
    """
    Return False for zero-variance or surrogate-ID columns.
    Used for the correlation heatmap — OHE and boolean columns ARE included.
    """
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.nunique() <= 1:
        return False
    n = len(series)
    if n > 0:
        col_lower = col.lower()
        if series.nunique() / n >= SEMANTIC_ID_CARDINALITY_THRESHOLD and any(
            pat in col_lower for pat in SEMANTIC_ID_NAME_PATTERNS
        ):
            return False
    return True


def _is_continuous_chart_safe(df: pd.DataFrame, col: str) -> bool:
    """
    Return False for zero-variance, surrogate-ID, or binary boolean columns.
    Used for histograms, box plots, and scatter matrices — keeps only
    continuous numeric columns; excludes OHE dummies and flag variables
    (e.g. is_refunded) which are uninformative in distribution charts.
    """
    if not _is_chart_safe(df, col):
        return False
    unique_vals = set(df[col].dropna().unique())
    if unique_vals <= {0, 1, True, False}:
        return False
    if _is_engineered_feature(col):
        return False
    return True


# Suffixes produced by the engineer agent's derived features. These are
# mathematically dependent on their source columns, so including them in
# distribution charts or correlation rankings produces misleading,
# tautological signal (a product correlates with its own factor).
_ENGINEERED_SUFFIXES = ("_log", "_freq")


def _is_engineered_feature(col: str) -> bool:
    """True for interaction terms (contain '_x_') or suffixed derived cols."""
    if "_x_" in col:
        return True
    return any(col.endswith(suf) for suf in _ENGINEERED_SUFFIXES)


# ---------------------------------------------------------------------------
# Deterministic insight generation
# ---------------------------------------------------------------------------

def _generate_insight(
    chart_type: str,
    df: pd.DataFrame,
    x_col: str | None,
    y_col: str | None,
    heatmap_cols: list[str] | None = None,
    *,
    outlier_iqr_multiplier: float = DEFAULT_OUTLIER_IQR_MULTIPLIER,
) -> str:
    """
    Generate one analytical sentence for a chart without an LLM call.

    Uses column statistics already computed from the DataFrame:
      histogram  — skewness + modelling implication
      box        — median, IQR, outlier count
      heatmap    — strongest correlated pair (correlation matrix only)
      line       — first/second half trend direction
      splom      — static summary
      scatter    — Spearman r between x and y
    Returns "" on any error so a missing insight never blocks rendering.

    outlier_iqr_multiplier: the SAME multiplier used by the real anomaly
    detector for this session (state["outlier_iqr_multiplier"], default
    DEFAULT_OUTLIER_IQR_MULTIPLIER). Previously this function used a
    hardcoded 1.5x fence for the box-plot outlier count regardless of what
    multiplier the user configured for actual detection, so the Overview/
    Audit tab and this narrative could disagree on how many outliers a
    column had (2026-07-03 architecture audit, decision log item 6).
    """
    try:
        if chart_type == "histogram" and x_col and x_col in df.columns:
            s = pd.to_numeric(df[x_col], errors="coerce").dropna()
            skew = float(s.skew())
            mean_v = float(s.mean())
            shape = ("right-skewed" if skew > STORYTELLER_SKEW_DIRECTION_THRESHOLD else
                     "left-skewed" if skew < -STORYTELLER_SKEW_DIRECTION_THRESHOLD else "symmetric")
            impl = ("A log transform may normalise this for modelling." if abs(skew) > 1.0
                    else "Distribution is suitable for linear models as-is.")
            return f"'{x_col}' is {shape} (skew={skew:.2f}, mean≈{mean_v:.3g}). {impl}"

        if chart_type == "box" and x_col and x_col in df.columns:
            s = pd.to_numeric(df[x_col], errors="coerce").dropna()
            q1, med, q3 = float(s.quantile(0.25)), float(s.median()), float(s.quantile(0.75))
            iqr = q3 - q1
            n_out = int(((s < q1 - outlier_iqr_multiplier * iqr) | (s > q3 + outlier_iqr_multiplier * iqr)).sum())
            out_note = (f"{n_out} outlier(s) flagged — review in the Audit Log." if n_out
                        else "No outliers; values cluster tightly around the median.")
            return f"Median={med:.3g}, IQR={iqr:.3g}. {out_note}"

        if chart_type == "heatmap" and heatmap_cols and len(heatmap_cols) >= 2:
            corr = df[heatmap_cols].corr()
            mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
            upper = corr.where(mask)
            flat = upper.stack()
            if flat.empty:
                return "Correlation matrix highlights linear relationships between all numeric features."
            abs_flat = flat.abs()
            top_pair = abs_flat.idxmax()
            top_r = float(flat.loc[top_pair])
            direction = "positive" if top_r > 0 else "negative"
            impl = ("High collinearity — consider dropping one feature for linear models."
                    if abs(top_r) > STORYTELLER_COLLINEARITY_THRESHOLD else
                    "Moderate association — potential candidate for an interaction feature.")
            return (f"Strongest pair: '{top_pair[0]}' & '{top_pair[1]}' "
                    f"({direction}, r={top_r:.2f}). {impl}")

        if chart_type == "line" and y_col and y_col in df.columns:
            s = pd.to_numeric(df[y_col], errors="coerce").dropna()
            if len(s) >= 4:
                h = len(s) // 2
                pct = (s.iloc[h:].mean() - s.iloc[:h].mean()) / (abs(s.iloc[:h].mean()) + 1e-9) * 100
                trend = ("upward" if pct > STORYTELLER_TREND_PCT_THRESHOLD
                         else "downward" if pct < -STORYTELLER_TREND_PCT_THRESHOLD else "flat")
                return f"'{y_col}' shows a {trend} trend ({pct:+.1f}% shift, second half vs first)."

        if chart_type == "splom":
            return ("Scatter matrix shows pairwise relationships across all continuous features. "
                    "Diagonal bands indicate strong correlation; clusters may reveal segmentation opportunities.")

        if chart_type in ("scatter", ) and x_col and y_col and x_col in df.columns and y_col in df.columns:
            xa = pd.to_numeric(df[x_col], errors="coerce")
            ya = pd.to_numeric(df[y_col], errors="coerce")
            mask2 = xa.notna() & ya.notna()
            if mask2.sum() >= 3:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    r, _ = sp_stats.spearmanr(xa[mask2], ya[mask2])
                r_f = float(r)
                strength = ("strong" if abs(r_f) > STORYTELLER_CORR_STRONG_THRESHOLD
                            else "moderate" if abs(r_f) > STORYTELLER_CORR_MODERATE_THRESHOLD else "weak")
                direction = "positive" if r_f > 0 else "negative"
                candidate = abs(r_f) > STORYTELLER_CORR_FEATURE_CANDIDATE_THRESHOLD
                return (f"Spearman r={r_f:.2f} ({strength} {direction} correlation). "
                        f"{'This relationship is a candidate model feature.' if candidate else 'Limited signal — consider polynomial or interaction features.'}")
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_storyteller(
    state: GraphState,
    *,
    llm: LLMProvider,
    auditor: Auditor,
) -> dict[str, Any]:
    """
    Build EDA portfolio; return chart_specs + narrative.

    Does not persist charts or the narrative to the database itself -- the
    caller (backend/api/analyze.py) does that after this function returns,
    using chart_specs and eda_narrative from the return dict. This keeps
    ai_engine free of backend.db.models imports (2026-07-03 architecture
    audit, decision log item 7).
    """
    df_eng = state.get("df_engineered")
    df: pd.DataFrame = df_eng if df_eng is not None else state["df_clean"]  # type: ignore[index]
    user_intent: str = state.get("user_intent") or ""  # type: ignore[assignment]

    # Same multiplier the anomaly detector used for this session — keeps the
    # box-plot outlier count consistent with the Overview/Audit tab instead
    # of a separate hardcoded value (2026-07-03 audit, decision log item 6).
    outlier_iqr_multiplier = float(state.get("outlier_iqr_multiplier", DEFAULT_OUTLIER_IQR_MULTIPLIER))  # type: ignore[call-overload]

    num_cols     = df.select_dtypes(include="number").columns.tolist()
    dt_cols      = [c for c in df.columns if str(df[c].dtype).startswith("datetime")]
    # heatmap_cols: continuous only -- excludes OHE dummies, binary flags,
    # zero-variance, and ID columns, so the heatmap isn't flooded with
    # redundant, structurally-identical columns that all correlate at +1.00.
    heatmap_cols = [c for c in num_cols if _is_continuous_chart_safe(df, c)]
    # cont_cols: also exclude binary boolean/OHE from box plots, histograms, splom
    cont_cols    = [c for c in num_cols if _is_continuous_chart_safe(df, c)]

    # Build imputed_cols: column → null_rate for columns filled by janitor
    _anomaly_by_id: dict[str, Any] = {
        str(a["anomaly_id"]): a  # type: ignore[literal-required]
        for a in (state.get("anomaly_report") or [])  # type: ignore[union-attr]
    }
    imputed_cols: dict[str, float] = {}
    for ch in (state.get("changes_applied") or []):  # type: ignore[union-attr]
        if ch.get("action") in ("fill_mean", "fill_median", "fill_mode"):
            anom = _anomaly_by_id.get(str(ch.get("anomaly_id", "")))
            if anom and anom.get("column_name") and anom.get("null_rate") is not None:
                imputed_cols[anom["column_name"]] = float(anom["null_rate"])  # type: ignore[index]

    # Plain-language summary of what the janitor actually did -- the narrative
    # is otherwise computed from df.isnull() AFTER cleaning, so a column that
    # was fully imputed or dropped for missing data looks indistinguishable
    # from a column that was never dirty in the first place.
    cleaning_actions: list[str] = []
    for ch in (state.get("changes_applied") or []):  # type: ignore[union-attr]
        act = ch.get("action")
        anom = _anomaly_by_id.get(str(ch.get("anomaly_id", "")))
        col = anom.get("column_name") if anom else None
        rows = anom.get("affected_rows") if anom else None
        if act in ("fill_mean", "fill_median", "fill_mode") and col:
            cleaning_actions.append(
                f"'{col}': {rows} missing value(s) imputed via {act.replace('fill_', '')}."
            )
        elif act == "drop_column" and col:
            cleaning_actions.append(
                f"'{col}': column dropped ({rows} missing value(s))."
            )
        elif act == "drop_rows" and col:
            cleaning_actions.append(
                f"'{col}': {rows} row(s) dropped for missing/invalid data."
            )
        elif act == "remove_duplicates":
            cleaning_actions.append(f"{rows} duplicate row(s) removed.")

    specs: list[ChartSpec] = []
    primary = await _llm_primary_chart(df, num_cols, user_intent, llm)
    if primary:
        specs.append(primary)

    # Histograms + box plots: continuous only (no binary/OHE columns)
    for col in cont_cols[: STORYTELLER_MAX_HISTO_COLS]:
        specs.append(_s("histogram", f"Distribution of {col}", col, None, None,
                        [{"type": "histogram", "x": _nums(df, col), "name": col}],
                        {"xaxis": {"title": col}, "yaxis": {"title": "Count"}}, 1,
                        insight=_generate_insight("histogram", df, col, None)))
        specs.append(_s("box", f"Box plot — {col}", col, None, None,
                        [{"type": "box", "y": _nums(df, col), "name": col, "boxpoints": "outliers"}],
                        {}, 2, insight=_generate_insight(
                            "box", df, col, None,
                            outlier_iqr_multiplier=outlier_iqr_multiplier)))

    # Correlation heatmap: include OHE binary columns so product_category_* appear.
    # Mask near-zero cells (|r| < STORYTELLER_HEATMAP_MIN_CORR) to 0 so the
    # matrix stays readable after OHE expansion produces many sparse columns.
    if len(heatmap_cols) >= 2:
        corr = df[heatmap_cols].corr().round(3)
        corr_masked = corr.where(corr.abs() >= STORYTELLER_HEATMAP_MIN_CORR, other=0.0)
        # Compute max label length for the frontend to size margins dynamically
        max_label_len = max(len(c) for c in heatmap_cols)
        z = sanitize_json(corr_masked.values.tolist())
        specs.append(_s("heatmap", "Correlation heatmap", None, None, None,
                        [{"type": "heatmap", "z": z,
                          "x": heatmap_cols, "y": heatmap_cols,
                          "colorscale": "RdBu", "zmid": 0}],
                        {"_max_label_len": max_label_len}, 3,
                        insight=_generate_insight("heatmap", df, None, None, heatmap_cols=heatmap_cols)))

    # Scatter matrix: continuous only (no binary/OHE or flag columns)
    if STORYTELLER_SCATTER_MIN_COLS <= len(cont_cols) <= STORYTELLER_SCATTER_MAX_COLS:
        dims = [{"label": c, "values": _nums(df, c)} for c in cont_cols]
        specs.append(_s("splom", "Scatter matrix", None, None, None,
                        [{"type": "splom", "dimensions": dims}], {}, 4,
                        insight=_generate_insight("splom", df, None, None)))

    for dt_col in dt_cols[:1]:
        if cont_cols:
            sub = _sample_df(df[[dt_col, cont_cols[0]]].dropna().sort_values(dt_col))
            specs.append(_s("line", f"{cont_cols[0]} over time", dt_col, cont_cols[0], None,
                            [{"type": "scatter", "mode": "lines",
                              "x": sub[dt_col].astype(str).tolist(),
                              "y": _nums(sub, cont_cols[0]), "name": cont_cols[0]}],
                            {"xaxis": {"title": dt_col}}, 5,
                            insight=_generate_insight("line", df, dt_col, cont_cols[0])))

    if df.isnull().any().any():
        nm = df.isnull().astype(int)
        specs.append(_s("heatmap", "Missingness heatmap", None, None, None,
                        [{"type": "heatmap", "z": nm.values.tolist(), "x": nm.columns.tolist(),
                          "colorscale": [[0, "#f0f9ff"], [1, "#dc2626"]], "showscale": False}],
                        {}, 6))

    narrative = _build_narrative(df, num_cols, user_intent, imputed_cols=imputed_cols,
                                  cleaning_actions=cleaning_actions)

    # Auditor is the single writer of session.status (Section 6.4) — this
    # replaces the previous direct `session_row.status = "complete"` write,
    # which bypassed Auditor and was flagged in the 2026-07-03 architecture
    # audit (decision log item 9). Plain string, not the SessionStatus enum
    # (item 7) -- Auditor coerces internally.
    await auditor.update_session_status("complete")

    await auditor.log(agent_name="storyteller", phase="phase3",
                      action=f"Generated {len(specs)} charts", reason="EDA portfolio complete",
                      rows_affected=len(df))
    return {"chart_specs": specs, "eda_narrative": narrative}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_df(df: pd.DataFrame) -> pd.DataFrame:
    """Uniformly sample to STORYTELLER_MAX_CHART_ROWS rows for chart trace payloads.

    Keeps the full DataFrame for statistical calculations (correlations, narratives).
    Only call this when building Plotly trace data sent to the frontend.
    """
    if len(df) <= STORYTELLER_MAX_CHART_ROWS:
        return df
    return df.sample(n=STORYTELLER_MAX_CHART_ROWS, random_state=42)


def _nums(df: pd.DataFrame, col: str) -> list[float]:
    """Extract numeric values from a column, sampled to max chart rows."""
    return pd.to_numeric(_sample_df(df)[col], errors="coerce").dropna().tolist()


def _s(
    ctype: str, title: str,
    x: str | None, y: str | None, color: str | None,
    data: list[dict[str, Any]], extra_layout: dict[str, Any], order: int,
    insight: str = "",
) -> ChartSpec:
    layout: dict[str, Any] = {"title": title, **extra_layout}
    return {
        "chart_id": str(uuid.uuid4()),
        "chart_type": ctype, "title": title,
        "x_column": x, "y_column": y, "color_column": color,
        "plotly_config": {"data": data, "layout": layout},
        "display_order": order,
        "insight_text": insight,
    }


# ---------------------------------------------------------------------------
# LLM primary chart
# ---------------------------------------------------------------------------

async def _llm_primary_chart(
    df: pd.DataFrame, num_cols: list[str], user_intent: str, llm: LLMProvider,
) -> ChartSpec | None:
    col_summary = ", ".join(f"{c} ({df[c].dtype})" for c in df.columns[:20])
    prompt = (
        "You are an expert data visualisation advisor.\n"
        f"Dataset columns: {col_summary}\n"
        f"User intent: {user_intent or 'general exploration'}\n\n"
        "Select the SINGLE most informative chart. Respond with JSON:\n"
        '{"chart_type":"<scatter|bar|line|histogram|box>","x_column":"<col or null>",'
        '"y_column":"<col or null>","color_column":"<col or null>","title":"<short title>"}'
    )
    try:
        raw_str = await llm.complete(prompt, task="general")
        if not raw_str or not raw_str.strip():
            raise ValueError("LLM returned empty response")
        raw = json.loads(raw_str)
        sel = _PrimaryChartSelection.model_validate(raw)
        all_cols = set(df.columns)
        x = sel.x_column if sel.x_column in all_cols else (num_cols[0] if num_cols else None)
        y = sel.y_column if sel.y_column in all_cols else (num_cols[1] if len(num_cols) > 1 else None)
        color = sel.color_column if sel.color_column in all_cols else None

        df_s = _sample_df(df)  # sampled copy for trace data only
        trace: dict[str, Any] = {"name": sel.title, "type": sel.chart_type}
        if sel.chart_type in ("scatter", "line"):
            trace["mode"] = "markers" if sel.chart_type == "scatter" else "lines"
        if x:
            trace["x"] = df_s[x].tolist()
        if y:
            trace["y"] = _nums(df_s, y) if y in df_s.columns else []
        if color:
            trace["marker"] = {"color": df_s[color].astype(str).tolist()}

        return _s(sel.chart_type, sel.title, x, y, color,
                  [trace], {"xaxis": {"title": x or ""}, "yaxis": {"title": y or ""}}, 0)
    except Exception as exc:
        logger.warning("LLM primary chart selection failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------

def _build_narrative(
    df: pd.DataFrame,
    num_cols: list[str],
    user_intent: str,
    *,
    imputed_cols: dict[str, float] | None = None,
    cleaning_actions: list[str] | None = None,
) -> dict[str, Any]:
    top_corr: list[dict[str, Any]] = []
    corr_cols = [c for c in num_cols if _is_continuous_chart_safe(df, c)]
    if len(corr_cols) >= 2:
        pairs: list[tuple[float, str, str]] = []
        for i, a in enumerate(corr_cols):
            for b in corr_cols[i + 1:]:
                xa = pd.to_numeric(df[a], errors="coerce")
                xb = pd.to_numeric(df[b], errors="coerce")
                mask = xa.notna() & xb.notna()
                if mask.sum() >= 3:
                    # Suppress ConstantInputWarning — we filter NaN results below
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        r, _ = sp_stats.spearmanr(xa[mask], xb[mask])
                    r_float = float(r)
                    # Skip pairs where spearmanr returned NaN (constant column)
                    if math.isnan(r_float) or math.isinf(r_float):
                        continue
                    pairs.append((abs(r_float), a, b))
        for rv, a, b in sorted(pairs, reverse=True)[:3]:
            top_corr.append({"col_a": a, "col_b": b, "spearman_r": round(rv, 3)})

    null_rates = df.isnull().mean()
    hotspots = [
        {"column": c, "null_rate": round(float(null_rates[c]), 3)}
        for c in null_rates[null_rates > 0].sort_values(ascending=False).index[:5]
    ]

    null_pen = float(df.isnull().mean().mean())
    low_var = sum(1 for c in num_cols if pd.to_numeric(df[c], errors="coerce").std() == 0)
    ml_readiness = max(0.0, round(100.0 * (1 - null_pen) * (1 - low_var / max(len(num_cols), 1)), 1))

    il = user_intent.lower()
    if any(k in il for k in ("predict", "forecast", "model")):
        rec = "Predictive modelling is appropriate. Consider regression or classification after feature selection."
    elif any(k in il for k in ("cluster", "segment", "group")):
        rec = "Clustering is suitable. Standardise numeric features before applying k-means or DBSCAN."
    elif any(k in il for k in ("anomaly", "outlier", "fraud")):
        rec = "Anomaly detection is the next step. Isolation Forest or LOF work well on this feature set."
    else:
        rec = "Exploratory analysis is complete. Review correlations and missingness hotspots before modelling."

    notes: list[str] = []
    if null_pen > STORYTELLER_NULL_PENALTY_NOTE_THRESHOLD:
        notes.append(f"High null rate ({null_pen:.1%}) — imputation or column removal recommended.")
    if low_var > 0:
        notes.append(f"{low_var} zero-variance column(s) detected — excluded from charts, consider dropping.")
    if not top_corr:
        notes.append("No strong numeric correlations found — dataset may need feature engineering.")
    # Imputation variance warnings — filled columns with high original null rate
    for col, nr in (imputed_cols or {}).items():
        if nr > IMPUTATION_VARIANCE_WARN_THRESHOLD:
            notes.append(
                f"'{col}' had {nr:.1%} nulls filled by imputation — "
                f"its distribution is skewed toward the fill value; treat stats with caution."
            )

    # Cleaning facts lead the narrative -- prepended so the Overview doesn't
    # read as "No missing data detected" when the janitor already fixed it.
    if cleaning_actions:
        notes = list(cleaning_actions) + notes

    cat_cols = [c for c in df.columns if str(df[c].dtype) in ("object", "category")]
    dt_cols  = [c for c in df.columns if str(df[c].dtype).startswith("datetime")]

    column_stats: list[dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        num_series = pd.to_numeric(series, errors="coerce")
        is_numeric = col in num_cols
        has_data = is_numeric and num_series.notna().any()
        null_count = int(series.isna().sum())

        def _s_float(v: Any) -> float | None:
            try:
                f = float(v)
                return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
            except Exception:
                return None

        column_stats.append({
            "name":         col,
            "dtype":        str(series.dtype),
            "null_count":   null_count,
            "null_rate":    round(float(series.isna().mean()), 4),
            "unique_count": int(series.nunique(dropna=True)),
            "mean":         _s_float(num_series.mean())     if has_data else None,
            "std":          _s_float(num_series.std())      if has_data else None,
            "min":          _s_float(num_series.min())      if has_data else None,
            "max":          _s_float(num_series.max())      if has_data else None,
            "skewness":     _s_float(num_series.skew())     if has_data else None,
            "kurtosis":     _s_float(num_series.kurtosis()) if has_data else None,
        })

    return {
        "top_correlations":      top_corr,
        "missingness_hotspots":  hotspots,
        "column_stats":          column_stats,
        "anomaly_notes":         notes,
        "ml_readiness_score":    ml_readiness,
        "ml_readiness_notes":    notes,
        "intent_recommendation": rec,
        "row_count":             len(df),
        "col_count":             len(df.columns),
        "numeric_cols":          num_cols,
        "categorical_cols":      cat_cols,
        "datetime_cols":         dt_cols,
        "cleaning_summary":      cleaning_actions or [],
    }
