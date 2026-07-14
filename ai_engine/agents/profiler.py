"""
ai_engine/agents/profiler.py

Profiler agent -- Phase 1, Step 3.

Uses the LLM to generate domain-aware semantic bounds for every numeric
column in the dataset.  These bounds are later used by the Orchestrator
to detect LOGICAL_VIOLATION anomalies (values outside plausible range).
The LLM is given the column name, basic statistics, and sample values.
It returns the valid domain min/max and a plain-English description.

Example: column 'age' -> {min_bound: 0, max_bound: 120,
description: 'Human age in years'}.

Wide datasets are processed in batches of PROFILE_BATCH_SIZE columns per
LLM call to stay within context window limits.

LLM usage rule: The LLM outputs bounds only.  All statistics passed to
the LLM are computed deterministically from Pandas -- the LLM never
calculates numbers, only interprets them.

RETRY POLICY (IMPORTANT -- read before adding retries here):
    This module does NOT retry LLM calls itself. llm.complete_json() is
    backed by the provider chain in ai_engine/llm/factory.py, which already
    encapsulates:
        1. Gemini native structured-output mode (schema-constrained, so it
           cannot return malformed/prose-wrapped JSON -- this replaces the
           old manual json.loads()/markdown-strip approach, which was the
           actual source of the JSONDecodeError seen on wide datasets)
        2. Gemini's own internal retry + exponential backoff on 429s
        3. Automatic failover to Ollama if Gemini exhausts its retries

    A prior version of this file added a second 3-attempt retry loop on
    top of that chain, plus a "fallback to Gemini" step that (due to
    provider caching in factory.py) re-invoked the *same* chain instance
    a 4th time. That stacked backoff windows on top of each other and
    turned a single rate-limited batch into minutes of hanging retries.

    One call in, one call out. If it fails, skip the batch -- don't retry
    here.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import BaseModel, ValidationError

from ai_engine.config import PROFILE_BATCH_SIZE
from ai_engine.graph.state import GraphState
from ai_engine.llm.base import LLMProvider, LLMProviderError
from ai_engine.agents.auditor import Auditor

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a data domain expert. Given column statistics and sample values, "
    "return the valid semantic bounds for each column as JSON. "
    "Bounds should reflect real-world validity (e.g. age: 0-120), not just "
    "the observed data range. Be conservative -- prefer wider bounds over narrow. "
    "Keep each description under 8 words to minimise output size."
)

# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------


class ColumnBounds(BaseModel):
    """Semantic validity bounds for a single numeric column."""

    min_bound: float
    max_bound: float
    description: str  # Plain-English domain description, e.g. "Human age in years"


class ProfileResponse(BaseModel):
    """LLM response containing bounds for a batch of columns."""

    columns: dict[str, ColumnBounds]


# ---------------------------------------------------------------------------
# Batch completion -- single call, no local retry layer (see module docstring)
# ---------------------------------------------------------------------------


async def _complete_profile_batch(
    prompt: str,
    llm: LLMProvider,
) -> ProfileResponse | None:
    """
    Obtain a validated ProfileResponse for one batch via native structured
    output. Returns None on failure (after the provider chain's own
    retries/fallback are exhausted) rather than raising, so the caller can
    skip this batch's columns while keeping bounds already collected from
    other batches.
    """
    try:
        return await llm.complete_json(
            prompt, ProfileResponse, system=_SYSTEM_PROMPT, task="profiling"
        )
    except (LLMProviderError, ValidationError) as exc:
        logger.warning(
            "Profiler batch failed after provider-level retries/fallback "
            "(%s: %s) -- skipping this batch's columns",
            type(exc).__name__, exc,
        )
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_profiler(
    state: GraphState,
    *,
    llm: LLMProvider,
    auditor: Auditor,
) -> dict[str, Any]:
    """
    Run the Profiler agent on the working DataFrame.

    Calls the LLM once per batch via structured output. A failed batch is
    skipped (its columns simply get no domain bounds) -- it does NOT abort
    bounds already collected for other batches, and does NOT retry the
    whole pipeline stage.

    Args:
        state:   Current GraphState. Must contain df_working and user_intent.
        llm:     Active LLMProvider instance.
        auditor: Auditor instance for this session.

    Returns:
        Partial GraphState dict: {'domain_profile': dict[str, dict]}
    """
    df: pd.DataFrame = state["df_working"]
    user_intent: str = state.get("user_intent", "")  # type: ignore[call-overload]

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        logger.info("Profiler: no numeric columns found -- skipping domain profiling")
        return {"domain_profile": {}}

    domain_profile: dict[str, dict[str, Any]] = {}
    total_batches = -(-len(numeric_cols) // PROFILE_BATCH_SIZE)
    failed_batches = 0

    for i in range(0, len(numeric_cols), PROFILE_BATCH_SIZE):
        batch = numeric_cols[i : i + PROFILE_BATCH_SIZE]
        prompt = _build_profile_prompt(df, batch, user_intent)
        response = await _complete_profile_batch(prompt, llm)

        if response is None:
            failed_batches += 1
            continue  # keep whatever domain_profile already has; move on

        for col, bounds in response.columns.items():
            if col in df.columns:
                domain_profile[col] = bounds.model_dump()

    profiled_count = len(domain_profile)
    numeric_count = len(numeric_cols)
    fully_profiled = failed_batches == 0 and profiled_count == numeric_count
    if fully_profiled:
        logger.info(
            "Profiler: generated bounds for %d/%d numeric columns",
            profiled_count, numeric_count,
        )
        audit_action = f"Domain profiling completed for all {profiled_count} numeric column(s)"
        audit_reason = (
            "LLM generated semantic validity bounds per column, enabling "
            "logical-violation detection (out-of-range values such as negative ages)."
        )
    else:
        missing = numeric_count - profiled_count
        logger.warning(
            "Profiler DEGRADED: bounds for only %d/%d numeric columns "
            "(%d/%d batches failed) -- logical-violation checks disabled for %d column(s)",
            profiled_count, numeric_count, failed_batches, total_batches, missing,
        )
        audit_action = (
            f"Domain profiling DEGRADED: bounds for {profiled_count}/{numeric_count} "
            f"numeric column(s)"
            + (f" ({failed_batches}/{total_batches} batches failed after provider "
               f"retries/fallback)" if failed_batches else "")
        )
        audit_reason = (
            f"LLM domain profiling produced no bounds for {missing} numeric column(s), "
            "so logical-violation detection (out-of-range values such as negative ages "
            "or impossible readings) is DISABLED for those column(s) this run. This "
            "usually means the LLM provider was unavailable (e.g. Ollama not running "
            "and no Gemini key/quota available)."
        )
    await auditor.log(
        agent_name="profiler",
        phase="phase1",
        action=audit_action,
        reason=audit_reason,
        rows_affected=0,
        is_llm_decision=True,
        llm_prompt_summary=(
            f"Batched domain profiling -- {numeric_count} column(s) in "
            f"{total_batches} batch(es)"
        ),
    )
    return {"domain_profile": domain_profile}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_profile_prompt(
    df: pd.DataFrame,
    columns: list[str],
    user_intent: str,
) -> str:
    """Build a batched profiling prompt describing a set of numeric columns."""
    lines = [
        f"Dataset context: {user_intent or 'No intent provided.'}",
        "",
        "For each column below, return the valid semantic min and max bounds.",
        "Return a JSON object with key 'columns' mapping column name to",
        "{min_bound, max_bound, description}. Keep descriptions under 8 words.",
        "",
        "Columns:",
    ]
    for col in columns:
        series = df[col].dropna()
        if series.empty:
            continue
        # Send only computed statistics -- no raw data rows.
        # This keeps the prompt small regardless of dataset size.
        lines.append(
            f"  - {col}: min={series.min():.4g}, max={series.max():.4g}, "
            f"mean={series.mean():.4g}, std={series.std():.4g}, "
            f"median={series.median():.4g}, "
            f"p25={series.quantile(0.25):.4g}, p75={series.quantile(0.75):.4g}"
        )
    return "\n".join(lines)
