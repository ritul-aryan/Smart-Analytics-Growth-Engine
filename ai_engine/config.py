"""
ai_engine/config.py

AI-engine constants and default thresholds.

This module is the single source of truth for every algorithmic parameter
in the MAE agent pipeline.  No agent, no LLM provider, and no feature
engineering function may hardcode a numeric threshold.  All values live here.

Categories:
    LLM generation   — model names, temperature, token limits, retry policy
    Anomaly detection — IQR multiplier, null density threshold, PII patterns
    Feature engineering — OHE, log transform, interaction term defaults
    Quality scoring  — per-anomaly-type penalty weights and caps
    Prompt constants — max characters, few-shot example counts
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# LLM — model identifiers
# ---------------------------------------------------------------------------

GEMINI_PRIMARY_MODEL: str = "gemini-2.0-flash"
GEMINI_BACKUP_MODEL: str = "gemini-1.5-flash-latest"  # kept for reference; not in active retry chain

OLLAMA_ROUTER_MODEL: str = "qwen2.5-coder:7b"
OLLAMA_STORYTELLER_MODEL: str = "llama3.1:8b"

OLLAMA_STORYTELLER_TASKS: frozenset[str] = frozenset({"storytelling", "profiling", "narrative"})
OLLAMA_ROUTER_TASKS: frozenset[str] = frozenset({"routing", "general", "normalisation"})

# ---------------------------------------------------------------------------
# LLM — generation parameters
# ---------------------------------------------------------------------------

GEMINI_TEMPERATURE: float = 0.2
GEMINI_MAX_OUTPUT_TOKENS: int = 4096  # Raised from 2048: gives batched profiler
                                           # responses headroom to avoid mid-object truncation.

OLLAMA_TEMPERATURE: float = 0.1
OLLAMA_MAX_TOKENS: int = 2048

LLM_MAX_RETRIES: int = 3
LLM_RETRY_DELAY_SECONDS: float = 2.0

# Rate-limit backoff (429 / ResourceExhausted).
# Wait = min(BASE * 2^attempt + uniform(0,1), MAX) before retrying Gemini.
# After LLM_MAX_RETRIES the chain falls back to Ollama.
LLM_RATE_LIMIT_BASE_DELAY: float = 4.0   # seconds; doubles each attempt
LLM_RATE_LIMIT_MAX_DELAY: float = 30.0   # per-attempt cap

# Max simultaneous LLM calls across all providers and pipeline instances.
# Enforced via asyncio.Semaphore in ai_engine/llm/base.py.
LLM_CONCURRENT_CALLS: int = 2

# ---------------------------------------------------------------------------
# Anomaly detection — 5-tier pipeline constants
# ---------------------------------------------------------------------------

ZERO_MEANINGFUL_KEYWORDS: frozenset[str] = frozenset({
    "count", "quantity", "qty", "num", "number", "total", "flag", "indicator",
    "binary", "bool", "is_", "has_",
})

DEFAULT_OUTLIER_IQR_MULTIPLIER: float = 3.0
OUTLIER_IQR_MULTIPLIER_MIN: float = 1.5
OUTLIER_IQR_MULTIPLIER_MAX: float = 5.0

DEFAULT_NULL_DENSITY_ROW_THRESHOLD: float = 0.50
NULL_DENSITY_THRESHOLD_MIN: float = 0.10
NULL_DENSITY_THRESHOLD_MAX: float = 0.90

MISSING_DATA_DANGER_NULL_RATE: float = 0.40

PII_REGEX_PATTERNS: dict[str, str] = {
    "email":       r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "phone":       r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn":         r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
}

PII_SAMPLE_SIZE: int = 100

ROW_LIMIT_SOFT_WARNING: int = 50_000

# ---------------------------------------------------------------------------
# Feature engineering — Engineer agent thresholds
# ---------------------------------------------------------------------------

DEFAULT_OHE_MAX_UNIQUE: int = 10  # Stricter cap prevents cardinality bloat on Telecom/multi-label datasets
OHE_MAX_UNIQUE_MIN: int = 2
OHE_MAX_UNIQUE_MAX: int = 50

DEFAULT_LOG_SKEW_THRESHOLD: float = 1.5
LOG_SKEW_THRESHOLD_MIN: float = 0.5
LOG_SKEW_THRESHOLD_MAX: float = 5.0

DEFAULT_CORRELATION_THRESHOLD: float = 0.50
CORRELATION_THRESHOLD_MIN: float = 0.10
CORRELATION_THRESHOLD_MAX: float = 0.99

ENGINEER_MIN_UNIQUE_FOR_TRANSFORM: int = 10
ENGINEER_LOG_SKEW_THRESHOLD: float = DEFAULT_LOG_SKEW_THRESHOLD
ENGINEER_INTERACTION_MIN_R: float = DEFAULT_CORRELATION_THRESHOLD

# High-cardinality fallback (Sprint 5): categorical columns whose cardinality
# exceeds the OHE cap but is <= this bound receive FREQUENCY encoding
# (category replaced by its occurrence count in a new column) instead of
# being skipped outright. Above this bound the column is skipped entirely.
DEFAULT_FREQ_ENCODING_MAX_UNIQUE: int = 50

# Object-dtype (string) columns qualify for datetime extraction only when
# their name looks time-like AND at least this fraction of non-null values
# parses successfully with pd.to_datetime. Guards against the prototype's
# "1970 features" bug resurfacing via aggressive string coercion.
DATETIME_PARSE_MIN_SUCCESS_RATE: float = 0.80

# ---------------------------------------------------------------------------
# Quality scoring — weighted penalty model
# ---------------------------------------------------------------------------

QUALITY_PENALTY_WEIGHTS: dict[str, float] = {
    "DUPLICATE_ROWS":         0.30,
    "MISSING_DATA":           0.25,
    "ZERO_AS_MISSING":        0.10,
    "LOGICAL_VIOLATION":      0.20,
    "STATISTICAL_OUTLIER":    0.10,
    "HIGH_NULL_DENSITY_ROWS": 0.15,
    "PII_DETECTED":           0.05,
}

QUALITY_PENALTY_CAPS: dict[str, float] = {
    "DUPLICATE_ROWS":         30.0,
    "MISSING_DATA":           25.0,
    "ZERO_AS_MISSING":        10.0,
    "LOGICAL_VIOLATION":      20.0,
    "STATISTICAL_OUTLIER":    10.0,
    "HIGH_NULL_DENSITY_ROWS": 15.0,
    "PII_DETECTED":            5.0,
}

# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

SEVERITY_HIGH_THRESHOLD: float = 0.20
SEVERITY_MEDIUM_THRESHOLD: float = 0.05
PII_SEVERITY: str = "high"

# ---------------------------------------------------------------------------
# Prompt engineering — context budget
# ---------------------------------------------------------------------------

METADATA_SUMMARY_MAX_CHARS: int = 1_500
PROFILE_SAMPLE_SIZE: int = 10
PROFILE_BATCH_SIZE: int = 10  # Lowered from 20: wide files (e.g. Telecom) were
                                  # producing responses that exceeded GEMINI_MAX_OUTPUT_TOKENS,
                                  # causing truncated/malformed JSON mid-batch.

# ---------------------------------------------------------------------------
# Storyteller — EDA portfolio limits
# ---------------------------------------------------------------------------

STORYTELLER_MAX_HISTO_COLS: int = 8
STORYTELLER_SCATTER_MIN_COLS: int = 2
STORYTELLER_SCATTER_MAX_COLS: int = 8
# Maximum rows serialised into a single chart trace (prevents oversized JSON payloads).
# Datasets larger than this are uniformly sampled before building Plotly traces.
STORYTELLER_MAX_CHART_ROWS: int = 5_000
# Minimum absolute Pearson |r| to display a cell in the correlation heatmap.
# Near-zero correlations are masked to 0 to keep the matrix readable after OHE expansion.
STORYTELLER_HEATMAP_MIN_CORR: float = 0.20

# ---------------------------------------------------------------------------
# Semantic type classification — Engineer and Orchestrator agents
# ---------------------------------------------------------------------------

# Substrings in a column name that signal a primary-key / surrogate-ID column.
# Engineer skips log-transform and datetime extraction for these columns.
SEMANTIC_ID_NAME_PATTERNS: frozenset[str] = frozenset({
    "id", "key", "pk", "index", "idx", "code", "nr", "no",
})

# Substrings that signal a Unix-timestamp column.
# Datetime extraction fires ONLY when BOTH name AND value range match.
SEMANTIC_TIMESTAMP_NAME_PATTERNS: frozenset[str] = frozenset({
    "time", "ts", "timestamp", "date", "created", "updated",
    "modified", "epoch",
})

# Substrings whose physical domain enforces a non-negative floor.
# Janitor clamps IQR lower_fence to max(lower_fence, 0) for these.
SEMANTIC_NONNEG_DOMAIN_PATTERNS: frozenset[str] = frozenset({
    "age", "revenue", "price", "amount", "cost", "salary",
    "duration", "count", "qty", "quantity", "distance",
    "weight", "height", "rate", "score", "balance",
})

# Substrings where zero is ALWAYS a valid business value (never a null proxy).
# Orchestrator never flags zeros in these columns as ZERO_AS_MISSING.
SEMANTIC_ZERO_ALWAYS_VALID_PATTERNS: frozenset[str] = frozenset({
    "revenue", "price", "amount", "cost", "sales", "discount",
    "refund", "balance", "credit", "debit",
})

# Unix-epoch second range used to confirm a column holds timestamp data.
SEMANTIC_UNIX_TS_MIN: float = 1_000_000_000.0   # 2001-09-09
SEMANTIC_UNIX_TS_MAX: float = 9_999_999_999.0   # 2286-11-20

# Cardinality ratio above which an integer column is treated as a surrogate ID.
SEMANTIC_ID_CARDINALITY_THRESHOLD: float = 0.95

# ---------------------------------------------------------------------------
# Visualization guardrails — Storyteller agent
# ---------------------------------------------------------------------------

# Columns whose null rate exceeded this threshold at imputation time get a
# variance-skew warning in the EDA narrative (fill value may dominate the dist).
IMPUTATION_VARIANCE_WARN_THRESHOLD: float = 0.20

# ---------------------------------------------------------------------------
# Storyteller — deterministic insight-text thresholds
#
# Added 2026-07-03 (architecture audit decision log item 6). These were
# previously hardcoded numeric literals inside _generate_insight() and
# _build_narrative() in ai_engine/agents/storyteller.py. The box-plot outlier
# count specifically used a hardcoded 1.5x IQR fence that conflicted with the
# governed outlier_iqr_multiplier (default 3.0, user-configurable) used by
# the real anomaly detector — meaning the Overview/Audit tab and the EDA
# narrative tab could report different outlier counts for the same dataset.
# Storyteller now reads the session's actual outlier_iqr_multiplier for that
# calculation instead of a separate hardcoded value; see DEFAULT_OUTLIER_IQR_MULTIPLIER
# above for the fallback default. The rest of these are narrative-text
# categorisation cutoffs ("strong" vs "moderate" correlation, "upward" vs
# "flat" trend, etc.) — not user-configurable, but centralised here per the
# project's no-magic-numbers rule.
# ---------------------------------------------------------------------------

# |skewness| above which a histogram insight is described as skewed rather
# than symmetric.
STORYTELLER_SKEW_DIRECTION_THRESHOLD: float = 0.5

# Absolute Spearman r bands used to describe a correlation's strength in
# scatter-chart insight text.
STORYTELLER_CORR_STRONG_THRESHOLD: float = 0.7
STORYTELLER_CORR_MODERATE_THRESHOLD: float = 0.4

# Absolute Spearman r above which a scatter-chart insight calls the
# relationship a "candidate model feature".
STORYTELLER_CORR_FEATURE_CANDIDATE_THRESHOLD: float = 0.5

# Absolute correlation above which a heatmap insight warns of high
# collinearity rather than suggesting an interaction feature.
STORYTELLER_COLLINEARITY_THRESHOLD: float = 0.8

# Percent shift (second half vs. first half of a time series) above/below
# which a line-chart insight calls the trend "upward"/"downward" rather
# than "flat".
STORYTELLER_TREND_PCT_THRESHOLD: float = 5.0

# Mean null-rate across the whole dataset above which the EDA narrative adds
# a "high null rate" note. Conceptually related to but distinct from
# NULL_DENSITY_THRESHOLD (which is a per-row anomaly detection cutoff) —
# this one scores the dataset as a whole for the narrative panel.
STORYTELLER_NULL_PENALTY_NOTE_THRESHOLD: float = 0.10

# ---------------------------------------------------------------------------
# Janitor — imputation heuristics
# ---------------------------------------------------------------------------

# nunique() above which a numeric column is treated as "continuous" for the
# fill_mode override rule (mode imputation is overridden to median for
# continuous columns — see ai_engine/agents/janitor.py::_fill_missing).
# Deliberately independent from DEFAULT_OHE_MAX_UNIQUE: that threshold is
# Engineer's user-configurable OHE cutoff and applies to categorical columns;
# coupling the two would make Janitor's imputation behaviour silently shift
# whenever a user changes the OHE setting for an unrelated agent.
JANITOR_CONTINUOUS_CARDINALITY_THRESHOLD: int = 10

# ---------------------------------------------------------------------------
# Orchestrator — metadata summary
# ---------------------------------------------------------------------------

# Max columns listed per dtype group (numeric / categorical) in the compact
# metadata_summary string passed to later LLM calls. Purely a display/prompt-
# size limit, not a detection threshold.
METADATA_SUMMARY_MAX_COLUMNS_LISTED: int = 10

# ---------------------------------------------------------------------------
# File ingestion
# ---------------------------------------------------------------------------

# Encoding fallback order for pd.read_csv.
# Real-world Kaggle / government datasets frequently use latin-1 or cp1252
# instead of utf-8. Each encoding is tried in order; the first that succeeds
# without a UnicodeDecodeError is used. Both latin-1 and cp1252 are strict
# supersets of ASCII so they never silently corrupt ASCII-only files.
CSV_ENCODING_FALLBACKS: list[str] = ["utf-8", "latin-1", "cp1252"]