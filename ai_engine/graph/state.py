"""
ai_engine/graph/state.py — GraphState shared data bag for the MAE pipeline.

This is the single shared data bag passed between all LangGraph nodes
(Section 6.1 of MAE_Master_Architecture_v2.docx). LangGraph owns this state
during a run; the sessions/anomalies/audit_log/files/charts/chat_messages
tables own persistent state between runs. These two stores must not overlap.

Only `session_id` and `llm_provider` are guaranteed present at every graph
entry point. Phase 1 (`phase1_app`) and Phase 2+3 (`phase2_app`) start from
different subsets of this bag — Phase 1 enters with `file_path` and no
`anomaly_report`; Phase 2+3 enters with `df_working` and `anomaly_report`
already loaded from the database and no `file_path` at all. Every field
beyond the two always-present keys is `NotRequired` and MUST be read with
`.get()`, never direct subscript, unless the calling node is downstream of
the phase that guarantees it exists.
"""

from __future__ import annotations

import sys
from typing import Any, TypedDict

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired


class AnomalyRecord(TypedDict):
    """One detected anomaly, as produced by Orchestrator Step 5 (Section 6.2)
    and re-hydrated from the `anomalies` table when Phase 2+3 starts."""

    anomaly_id: str
    anomaly_type: str
    column_name: str | None
    affected_rows: int
    null_rate: float | None
    severity: str
    details: dict[str, Any]
    display_order: int
    is_supplementary: NotRequired[bool]


class UserDecision(TypedDict):
    """One HITL decision submitted via POST /api/analyze/complete (Section 6.3)."""

    anomaly_id: str
    action: str
    params: NotRequired[dict[str, Any] | None]


class ChangeRecord(TypedDict):
    """One transformation applied by the Janitor agent (Section 6.4)."""

    anomaly_id: str
    action: str
    description: str


class FeatureRecord(TypedDict):
    """One feature-engineering step applied by the Engineer agent (Section 6.4)."""

    transform_type: str
    source_columns: list[str]
    output_columns: list[str]
    description: str


class ChartSpec(TypedDict):
    """One Plotly chart produced by the Storyteller agent (Section 6.4, 8.2)."""

    chart_id: str
    chart_type: str
    title: str
    x_column: str | None
    y_column: str | None
    color_column: str | None
    plotly_config: dict[str, Any]
    display_order: int
    insight_text: str


class GraphState(TypedDict):
    """Shared data bag passed between all LangGraph nodes."""

    # Always present — set at graph entry regardless of which phase is running
    session_id: str
    llm_provider: str

    # Phase 1 entry inputs — absent when entering Phase 2+3 (which loads
    # df_working and anomaly_report from the database instead of a file path)
    file_path: NotRequired[str]
    user_intent: NotRequired[str]

    # Phase 1 outputs — Orchestrator (Steps 1, 2, 4, 5, 6) + Profiler (Step 3)
    df_raw: NotRequired[Any]
    df_working: NotRequired[Any]
    column_renames: NotRequired[dict[str, str]]
    domain_profile: NotRequired[dict[str, Any]]
    zero_analysis: NotRequired[dict[str, str]]
    anomaly_report: NotRequired[list[AnomalyRecord]]
    quality_score_before: NotRequired[float]
    metadata_summary: NotRequired[str]

    # User-configurable thresholds (Section 8.3). Injected into the entry
    # state dict by backend/api/analyze.py from the request's Form fields;
    # read via state.get(key, <ai_engine/config.py default>) by Orchestrator
    # and Engineer. Declared explicitly here (2026-07-03 architecture audit
    # flagged these as previously undeclared, typo-prone dict keys).
    ohe_max_unique: NotRequired[int]
    log_skew_threshold: NotRequired[float]
    correlation_threshold: NotRequired[float]
    outlier_iqr_multiplier: NotRequired[float]
    null_density_threshold: NotRequired[float]

    # Phase 2 inputs — populated from the `anomalies` table after HITL review
    user_decisions: NotRequired[list[UserDecision]]

    # Phase 2 outputs — Janitor
    df_clean: NotRequired[Any]
    clean_file_path: NotRequired[str]
    quality_score_after: NotRequired[float]
    changes_applied: NotRequired[list[ChangeRecord]]

    # Phase 2.5 outputs — Engineer
    df_engineered: NotRequired[Any]
    engineered_file_path: NotRequired[str]
    fe_report: NotRequired[list[FeatureRecord]]

    # Phase 3 outputs — Storyteller
    chart_specs: NotRequired[list[ChartSpec]]
    eda_narrative: NotRequired[dict[str, Any]]

    # Error handling — any node may set this
    error: NotRequired[str | None]
