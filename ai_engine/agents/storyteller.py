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


class _ChartNarrativeResponse(BaseModel):
    """Batched LLM domain-narrative response: maps chart title -> one paragraph.

    An empty string for a title means the model judged there was nothing
    genuinely dataset-specific to add beyond the deterministic statistics
    (the anti-filler rule). Such entries are dropped, not rendered.
    """

    narratives: dict[str, str]


_CHART_NARRATIVE_SYSTEM = (
    "You are a senior data scientist writing a short domain interpretation for each "
    "EDA chart. You are given each chart's title, type, columns, and the exact "
    "statistics already computed for it, plus the user's stated analysis intent. "
    "For each chart, add ONE short paragraph of genuinely useful, dataset-specific "
    "domain insight that goes BEYOND restating the statistics -- what the pattern "
    "plausibly means for this kind of data, or what to do next. "
    "STRICT RULES: (1) Never invent numbers, correlations, or facts not present in "
    "the provided statistics. (2) If a chart has nothing genuinely useful to add "
    "beyond the statistics already shown, return an EMPTY STRING for that chart -- "
    "do NOT pad, do NOT restate the stats, do NOT write filler. (3) Keep each "
    "paragraph under 60 words. Return a JSON object with key 'narratives' mapping "
    "each chart title (verbatim) to its paragraph (or empty string)."
)


async def _llm_chart_narratives(
    specs: list[ChartSpec],
    user_intent: str,
    llm: LLMProvider,
) -> dict[str, str]:
    """Return {chart_title: domain_paragraph} from ONE batched LLM call.

    Returns {} on any failure so the deterministic Piece-1 insight text is
    never blocked or degraded -- the domain layer is purely additive. Reuses
    the provider chain's fast-fail/Ollama-fallback (ai_engine/llm), so a
    rate-limited Gemini degrades to Ollama automatically, and a total LLM
    failure simply yields no domain narrative rather than an error.
    """
    if not specs:
        return {}

    lines = [
        f"User analysis intent: {user_intent or 'not specified'}.",
        "",
        "Charts (title | type | columns | computed statistics):",
    ]
    for sp in specs:
        cols = ", ".join(c for c in (sp.get("x_column"), sp.get("y_column"), sp.get("color_column")) if c) or "n/a"
        stats = (sp.get("insight_text") or "").replace("\n\n", " ")
        lines.append(f"- TITLE: {sp['title']} | TYPE: {sp['chart_type']} | COLUMNS: {cols} | STATS: {stats}")
    prompt = "\n".join(lines)

    try:
        resp = await llm.complete_json(
            prompt, _ChartNarrativeResponse,
            system=_CHART_NARRATIVE_SYSTEM, task="storytelling",
        )
        return dict(resp.narratives)
    except Exception as exc:  # noqa: BLE001 -- any failure must degrade silently
        logger.warning("LLM chart-narrative batch failed (%s: %s) -- "
                       "keeping deterministic insights only", type(exc).__name__, exc)
        return {}


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

def _fmt(v: Any) -> str:
    """Format a number for insight text: integers without a decimal, else 3 sig-figs."""
    try:
        f = float(v)
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
        return f"{f:.3g}"
    except Exception:
        return str(v)


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
    Generate a rich, multi-paragraph deterministic analysis for a chart
    without an LLM call. Every statistic is computed from the DataFrame; every
    technical term is explained in-line so a non-specialist can follow it.
    Sections are separated by blank lines and prefixed with an UPPERCASE label
    so the frontend can render them as headed blocks. Returns "" on any error
    so a missing insight never blocks chart rendering.

    outlier_iqr_multiplier: the SAME multiplier the real anomaly detector used
    for this session, so the box-plot outlier count matches the Audit Log
    (2026-07-03 architecture audit, decision log item 6).
    """
    try:
        if chart_type == "histogram" and x_col and x_col in df.columns:
            s = pd.to_numeric(df[x_col], errors="coerce").dropna()
            if s.empty:
                return ""
            n = int(s.size)
            skew = float(s.skew())
            kurt = float(s.kurtosis())
            mean_v = float(s.mean())
            med_v = float(s.median())
            std_v = float(s.std())
            cv = (std_v / abs(mean_v)) if mean_v else float("nan")
            if skew > STORYTELLER_SKEW_DIRECTION_THRESHOLD:
                shape = "right-skewed (a long tail of high values pulls the mean above the median)"
            elif skew < -STORYTELLER_SKEW_DIRECTION_THRESHOLD:
                shape = "left-skewed (a long tail of low values pulls the mean below the median)"
            else:
                shape = "approximately symmetric (values are balanced around the centre)"
            cv_desc = (
                "n/a" if cv != cv
                else "low — values are tightly grouped relative to their size" if cv < 0.3
                else "moderate" if cv < 0.7
                else "high — values are widely dispersed relative to their size"
            )
            centre_agree = (
                "close, consistent with the symmetric shape"
                if abs(mean_v - med_v) <= 0.1 * (std_v + 1e-9)
                else "noticeably apart, consistent with the skew noted above"
            )
            parts = [
                f"WHAT THIS SHOWS — A histogram of '{x_col}', i.e. how its {n:,} values are "
                f"distributed across their range. The x-axis groups values into bins; bar height "
                f"is how many rows fall in each bin.",
                f"SHAPE — The distribution is {shape}. Skewness = {skew:.2f}: skew measures "
                f"asymmetry, where 0 is perfectly symmetric, positive means a right tail, negative "
                f"a left tail, and |skew| > 1 is considered strongly skewed. Excess kurtosis = "
                f"{kurt:.2f}: this measures tailedness (how heavy the tails / how many extreme "
                f"values are present) relative to a normal distribution, where 0 matches a bell "
                f"curve, positive means heavier tails/more outliers, negative means lighter tails.",
                f"CENTRE & SPREAD — Mean = {_fmt(mean_v)}, median = {_fmt(med_v)}. The mean is the "
                f"arithmetic average; the median is the middle value and is more robust to extremes. "
                f"They are {centre_agree}. Standard deviation = {_fmt(std_v)} (the typical distance "
                f"of a value from the mean); coefficient of variation = {cv:.2f} ({cv_desc}).",
            ]
            if abs(skew) > 1.0:
                parts.append(
                    "MODELLING IMPLICATION — Because the column is strongly skewed, a log or "
                    "Box-Cox transform would compress the tail and bring the distribution closer to "
                    "normal, which typically helps linear/parametric models (linear regression, "
                    "logistic regression) that assume roughly symmetric inputs. Tree-based models "
                    "(random forest, gradient boosting) are insensitive to skew and need no transform."
                )
            else:
                parts.append(
                    "MODELLING IMPLICATION — The distribution is close enough to symmetric to be "
                    "used as-is in linear and parametric models without a transform. Standardisation "
                    "(subtract mean, divide by SD) is still advisable if you mix this with features "
                    "on different scales."
                )
            return "\n\n".join(parts)

        if chart_type == "box" and x_col and x_col in df.columns:
            s = pd.to_numeric(df[x_col], errors="coerce").dropna()
            if s.empty:
                return ""
            q1, med, q3 = float(s.quantile(0.25)), float(s.median()), float(s.quantile(0.75))
            iqr = q3 - q1
            lo = q1 - outlier_iqr_multiplier * iqr
            hi = q3 + outlier_iqr_multiplier * iqr
            n_out = int(((s < lo) | (s > hi)).sum())
            rng = float(s.max() - s.min())
            parts = [
                f"WHAT THIS SHOWS — A box plot of '{x_col}'. The box spans the interquartile range "
                f"(IQR): its lower edge is Q1 (25th percentile), the line inside is the median (50th "
                f"percentile), the upper edge is Q3 (75th percentile). The whiskers extend to values "
                f"within {_fmt(outlier_iqr_multiplier)}× the IQR of the box; points beyond them are "
                f"flagged as potential outliers.",
                f"QUARTILES — Q1 = {_fmt(q1)}, median = {_fmt(med)}, Q3 = {_fmt(q3)}. This means 25% "
                f"of values fall below {_fmt(q1)}, half below {_fmt(med)}, and 75% below {_fmt(q3)}. "
                f"The IQR (the middle-50% span) = {_fmt(iqr)}; full range = {_fmt(rng)}.",
            ]
            if n_out:
                parts.append(
                    f"OUTLIERS — {n_out:,} value(s) lie beyond {_fmt(outlier_iqr_multiplier)}× IQR "
                    f"from the box (below {_fmt(lo)} or above {_fmt(hi)}) and are flagged as "
                    f"statistical outliers. This uses the SAME multiplier as the anomaly detector, "
                    f"so this count matches the Audit Log. Review whether they are genuine extremes "
                    f"(keep) or data-entry errors (treat/clamp)."
                )
            else:
                spread = (
                    "spread fairly evenly across the range (IQR is a large fraction of the full "
                    "range — consistent with a uniform-like distribution)"
                    if rng > 0 and iqr / rng > 0.4
                    else "concentrated near the median (the middle 50% occupies only a small part "
                    "of the full range)"
                )
                parts.append(
                    f"OUTLIERS — None detected at {_fmt(outlier_iqr_multiplier)}× IQR. Values are {spread}."
                )
            return "\n\n".join(parts)

        if chart_type == "heatmap" and heatmap_cols and len(heatmap_cols) >= 2:
            corr = df[heatmap_cols].corr()
            mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
            flat = corr.where(mask).stack()
            if flat.empty:
                return ""
            top_pair = flat.abs().idxmax()
            top_r = float(flat.loc[top_pair])
            ar = abs(top_r)
            direction = (
                "positive (they tend to rise together)" if top_r > 0
                else "negative (as one rises, the other tends to fall)"
            )
            parts = [
                f"WHAT THIS SHOWS — A correlation heatmap across {len(heatmap_cols)} continuous "
                f"features. Each cell is the Pearson correlation coefficient r between two columns, "
                f"ranging from -1 (perfect inverse) through 0 (no linear relationship) to +1 "
                f"(perfect direct). Colour encodes sign and strength.",
                f"STRONGEST RELATIONSHIP — '{top_pair[0]}' and '{top_pair[1]}', r = {top_r:.2f}, "
                f"{direction}. r² = {top_r ** 2:.2f}, meaning about {top_r ** 2 * 100:.0f}% of the "
                f"variation in one is linearly explained by the other.",
            ]
            if ar > STORYTELLER_COLLINEARITY_THRESHOLD:
                parts.append(
                    "IMPLICATION — This is high collinearity. Two features carrying nearly the same "
                    "information can destabilise linear-model coefficients (multicollinearity); "
                    "consider dropping one or combining them. Tree models are unaffected."
                )
            elif ar >= 0.3:
                parts.append(
                    "IMPLICATION — A moderate association. Potentially useful as an interaction "
                    "feature, but the two features are not redundant."
                )
            else:
                parts.append(
                    "IMPLICATION — Even the strongest pair is weak, so there is little linear "
                    "redundancy between these features — each contributes largely independent "
                    "information. Note Pearson r only captures LINEAR association; non-linear "
                    "relationships could still exist and would not show here."
                )
            return "\n\n".join(parts)

        if chart_type == "line" and y_col and y_col in df.columns:
            s = pd.to_numeric(df[y_col], errors="coerce").dropna()
            if len(s) >= 4:
                h = len(s) // 2
                pct = (s.iloc[h:].mean() - s.iloc[:h].mean()) / (abs(s.iloc[:h].mean()) + 1e-9) * 100
                trend = (
                    "upward" if pct > STORYTELLER_TREND_PCT_THRESHOLD
                    else "downward" if pct < -STORYTELLER_TREND_PCT_THRESHOLD else "flat"
                )
                return (
                    f"WHAT THIS SHOWS — A time-ordered line of '{y_col}'.\n\n"
                    f"TREND — Comparing the mean of the second half of the series to the first half "
                    f"gives a {pct:+.1f}% shift, i.e. a {trend} trend. This is a coarse "
                    f"first-vs-second-half comparison, not a fitted regression; it flags direction, "
                    f"not statistical significance. Seasonality or short-term cycles would need a "
                    f"time-series decomposition to detect."
                )
            return ""

        if chart_type == "splom":
            return (
                "WHAT THIS SHOWS — A scatter-plot matrix (SPLOM): every continuous feature plotted "
                "against every other. Off-diagonal cells are pairwise scatter plots; the diagonal "
                "shows each feature's own distribution.\n\n"
                "HOW TO READ IT — Look for tight diagonal bands (strong linear correlation), curved "
                "bands (non-linear relationships that a single correlation number would miss), and "
                "separated clusters (possible sub-groups worth segmenting). Because it shows raw "
                "pairwise structure, it surfaces relationships that summaries like Pearson r can hide."
            )

        if chart_type in ("scatter",) and x_col and y_col and x_col in df.columns and y_col in df.columns:
            xa = pd.to_numeric(df[x_col], errors="coerce")
            ya = pd.to_numeric(df[y_col], errors="coerce")
            mask2 = xa.notna() & ya.notna()
            if mask2.sum() >= 3:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    r, _ = sp_stats.spearmanr(xa[mask2], ya[mask2])
                r_f = float(r)
                strength = (
                    "strong" if abs(r_f) > STORYTELLER_CORR_STRONG_THRESHOLD
                    else "moderate" if abs(r_f) > STORYTELLER_CORR_MODERATE_THRESHOLD else "weak"
                )
                direction = "positive" if r_f > 0 else "negative"
                candidate = abs(r_f) > STORYTELLER_CORR_FEATURE_CANDIDATE_THRESHOLD
                return (
                    f"WHAT THIS SHOWS — A scatter plot of '{y_col}' against '{x_col}', one point per row.\n\n"
                    f"RELATIONSHIP — Spearman r = {r_f:.2f} ({strength} {direction}). Spearman measures "
                    f"monotonic association on ranks (do they move together in order?), so unlike Pearson "
                    f"it also captures non-linear-but-consistent trends and resists outliers. "
                    f"{'This is a candidate model feature.' if candidate else 'Limited linear signal — a polynomial or interaction term may extract more.'}"
                )
        return ""
    except Exception:
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
    #
    # Count precedence: the janitor's actual "rows_changed" (what really changed
    # on the working frame) > the anomaly's true detection count (total_flagged)
    # > affected_rows (attribution). Wording reflects the real anomaly type and
    # action so zeros are not mislabelled as missing values.
    def _summary_count(ch: dict[str, Any], anom: dict[str, Any] | None) -> Any:
        if ch.get("rows_changed") is not None:
            return ch["rows_changed"]
        if anom:
            details = anom.get("details") or {}
            if details.get("total_flagged") is not None:
                return details["total_flagged"]
            return anom.get("affected_rows")
        return None

    cleaning_actions: list[str] = []
    for ch in (state.get("changes_applied") or []):  # type: ignore[union-attr]
        act = ch.get("action")
        anom = _anomaly_by_id.get(str(ch.get("anomaly_id", "")))
        col = anom.get("column_name") if anom else None
        atype = anom.get("anomaly_type") if anom else None
        rows = _summary_count(ch, anom)
        if act == "remove_duplicates":
            cleaning_actions.append(f"{rows} duplicate row(s) removed.")
        elif act == "drop_column" and col:
            cleaning_actions.append(f"'{col}': column dropped.")
        elif act == "drop_rows" and col:
            cleaning_actions.append(f"'{col}': {rows} row(s) dropped.")
        elif act == "treat_as_missing" and col:
            cleaning_actions.append(
                f"'{col}': {rows} out-of-range value(s) set to missing (NaN)."
            )
        elif act in ("clamp_bounds", "cap_iqr") and col:
            cleaning_actions.append(f"'{col}': {rows} out-of-range value(s) capped to bounds.")
        elif act in ("fill_mean", "fill_median", "fill_mode") and col:
            method = act.replace("fill_", "")
            if atype == "ZERO_AS_MISSING":
                cleaning_actions.append(
                    f"'{col}': {rows} zero(s) treated as missing and imputed via {method}."
                )
            else:
                cleaning_actions.append(
                    f"'{col}': {rows} missing value(s) imputed via {method}."
                )
        elif act in ("redact", "hash_sha256") and col:
            verb = "redacted" if act == "redact" else "hashed"
            cleaning_actions.append(f"'{col}': column {verb}.")

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

    # Skip notes: charts deliberately NOT generated because they carry no real
    # signal. Surfaced in the narrative so a smaller portfolio reads as an
    # intentional, honest choice rather than a missing feature.
    skipped_charts: list[str] = []

    # Correlation heatmap: only generate when at least one numeric pair exceeds
    # STORYTELLER_HEATMAP_MIN_CORR. A matrix where every |r| is near zero is
    # pure noise (its own caption would read "no meaningful association"), so
    # skip it and explain why instead of rendering an empty red/grey grid.
    heatmap_max_r = _max_offdiag_abs_r(df, heatmap_cols)
    if len(heatmap_cols) >= 2 and heatmap_max_r is not None and heatmap_max_r >= STORYTELLER_HEATMAP_MIN_CORR:
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
    elif len(heatmap_cols) >= 2:
        skipped_charts.append(
            f"Correlation heatmap omitted: no numeric pair reached |r| ≥ "
            f"{STORYTELLER_HEATMAP_MIN_CORR:.2f} (strongest was "
            f"{heatmap_max_r:.2f}), so there was no meaningful linear "
            f"relationship worth showing."
        )

    # Scatter matrix: continuous only (no binary/OHE or flag columns), AND only
    # when at least one pair shows real correlation -- a matrix of pure scatter
    # clouds with no association teaches nothing, so skip and explain it too.
    scatter_max_r = _max_offdiag_abs_r(df, cont_cols)
    if (STORYTELLER_SCATTER_MIN_COLS <= len(cont_cols) <= STORYTELLER_SCATTER_MAX_COLS
            and scatter_max_r is not None and scatter_max_r >= STORYTELLER_HEATMAP_MIN_CORR):
        dims = [{"label": c, "values": _nums(df, c)} for c in cont_cols]
        specs.append(_s("splom", "Scatter matrix", None, None, None,
                        [{"type": "splom", "dimensions": dims}], {}, 4,
                        insight=_generate_insight("splom", df, None, None)))
    elif STORYTELLER_SCATTER_MIN_COLS <= len(cont_cols) <= STORYTELLER_SCATTER_MAX_COLS:
        skipped_charts.append(
            f"Scatter matrix omitted: the continuous features showed no "
            f"pairwise correlation above |r| ≥ {STORYTELLER_HEATMAP_MIN_CORR:.2f}, "
            f"so a matrix of uncorrelated scatter clouds would not have been informative."
        )

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
    # Append chart-selection notes so the UI can explain why the portfolio is
    # smaller (intelligent selection), rather than leaving the user wondering.
    if skipped_charts:
        existing_notes = narrative.get("anomaly_notes") or []
        narrative["chart_selection_notes"] = skipped_charts
        narrative["anomaly_notes"] = list(existing_notes) + skipped_charts

    # Optional LLM domain-narrative layer (default ON). Adds one short,
    # dataset-specific paragraph per chart ON TOP of the deterministic insight,
    # via a SINGLE batched LLM call. Purely additive: any failure leaves the
    # Piece-1 deterministic text untouched. Flag defaults to True; when the
    # Advanced Settings toggle is later threaded through to Phase 2+3 it can
    # switch this off for speed. "DOMAIN INSIGHT — ..." uses the same
    # "LABEL — text" section format the frontend already renders.
    if state.get("enable_llm_chart_narrative", True):
        domain = await _llm_chart_narratives(specs, user_intent, llm)
        for spec in specs:
            extra = (domain.get(spec["title"], "") or "").strip()
            if extra:
                spec["insight_text"] = spec["insight_text"] + "\n\nDOMAIN INSIGHT — " + extra

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


def _max_offdiag_abs_r(df: pd.DataFrame, cols: list[str]) -> float | None:
    """Largest absolute pairwise Pearson |r| among cols, ignoring the diagonal.

    Returns None when there are fewer than 2 columns or no valid correlation
    can be computed. Used to decide whether a correlation-based chart carries
    any real signal before it is generated -- a heatmap or scatter matrix in
    which no pair exceeds STORYTELLER_HEATMAP_MIN_CORR shows the user nothing
    useful, so it is skipped and explained rather than rendered as noise.
    """
    if len(cols) < 2:
        return None
    corr = df[cols].corr().abs()
    mask = ~np.eye(len(cols), dtype=bool)
    vals = corr.values[mask]
    vals = vals[~np.isnan(vals)]
    return float(vals.max()) if len(vals) else None


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
def _parse_chart_json(raw_str: str) -> dict[str, Any]:
    """
    Parse the LLM's chart-selection response into a dict.
    llm.complete() returns free text (task="general"), so the model may wrap
    the JSON in ```json ... ``` fences or add prose. A bare json.loads() on
    that fails with "Expecting value: line 1 column 1 (char 0)". This strips
    fences and, as a last resort, extracts the outermost {...} object before
    parsing. On genuine failure it raises, so the caller's existing except
    branch falls back to the default (non-LLM) charts unchanged.
    """
    text = raw_str.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
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
        raw = _parse_chart_json(raw_str)
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

    # pandas 3.0 renamed the default string dtype's repr from "object" to
    # "str" -- without this, string/text columns were never recognised as
    # categorical, so categorical_cols always came back empty and the
    # Overview narrative silently omitted the categorical column count.
    cat_cols = [c for c in df.columns if str(df[c].dtype) in ("object", "category", "str")]
    dt_cols  = [c for c in df.columns if str(df[c].dtype).startswith("datetime")]

    column_stats: list[dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        num_series = pd.to_numeric(series, errors="coerce")
        is_numeric = col in num_cols
        has_data = is_numeric and num_series.notna().any()
        null_count = int(series.isna().sum())

        # Skew/kurtosis are meaningless on binary/indicator (0/1) columns such
        # as one-hot-encoded dummies -- a two-value column has no meaningful
        # shape. Detect that case (all non-null values are 0 or 1, at most two
        # distinct values) and suppress ONLY skew/kurt for it. Genuine numeric
        # columns (many distinct values) are unaffected.
        is_binary_indicator = False
        if has_data:
            nn = num_series.dropna()
            if nn.nunique() <= 2 and nn.isin((0, 1)).all():
                is_binary_indicator = True

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
            "skewness":     None if is_binary_indicator else (_s_float(num_series.skew())     if has_data else None),
            "kurtosis":     None if is_binary_indicator else (_s_float(num_series.kurtosis()) if has_data else None),
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
