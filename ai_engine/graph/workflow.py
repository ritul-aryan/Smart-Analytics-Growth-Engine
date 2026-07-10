"""
ai_engine/graph/workflow.py

LangGraph workflow definitions for the MAE agent pipeline (Section 6 of
MAE_Master_Architecture_v2.docx).

  phase1_app — Upload & Audit
    START -> orchestrator -> END
    Outputs: anomaly_report, quality_score_before, domain_profile

  phase2_app — Cleaning + Engineering + EDA (Janitor -> Engineer -> Storyteller)
    START -> janitor -> engineer -> storyteller -> END
    Outputs: df_clean, df_engineered, chart_specs, eda_narrative

Both graphs share the GraphState TypedDict as their state schema.

Node topology note (2026-07-03 architecture audit follow-up):
  run_phase1() in ai_engine/agents/orchestrator.py already calls
  run_profiler() internally as part of its Step 2 -> Step 3 sequence. It is
  one atomic, tested function that also owns the Bug 1 (mixed-type IQR) and
  Bug 2 (null_rate on MISSING_DATA) regression fixes. Section 6.2's stage
  table describes agent *responsibilities* per pipeline step, not a mandated
  LangGraph node boundary, so phase1_app wraps the whole of run_phase1() as
  a single "orchestrator" node rather than splitting it into separate
  "orchestrator" / "profiler" nodes. Splitting it would mean refactoring
  tested production code, which is out of scope for this pass — flagged for
  the user, not assumed silently.

Runtime dependency injection:
  Each agent function needs live, per-request resources (an LLMProvider
  instance, an Auditor bound to this session) that do not belong in
  GraphState -- they are not part of the persistent-vs-ephemeral state split
  described in Section 6. build_phase1_app() and build_phase2_app() are
  therefore factories: each call compiles a fresh graph whose nodes close
  over the caller's llm/auditor (and, for phase 2, processed_dir) for that
  one pipeline run.

  Neither factory accepts a db/AsyncSession parameter. As of the 2026-07-03
  architecture audit, decision log item 7, none of the wrapped agent
  functions (run_phase1, run_janitor, run_engineer, run_storyteller) touch
  the database directly -- persistence (anomalies, charts, narrative,
  session status fields) is handled by backend/api/analyze.py after each
  graph run, and status transitions go through Auditor.update_session_status().
  ai_engine therefore has no need for a live AsyncSession at all, keeping it
  free of any backend.db.models or backend.config imports.

  This replaces the previous placeholder implementation, where both graphs
  were compiled once at import time with `lambda state: state` no-op nodes
  and the API layer called the agent functions directly, bypassing LangGraph
  entirely (the gap flagged in the 2026-07-03 architecture audit, item 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph  # type: ignore[import]

from ai_engine.agents.auditor import Auditor
from ai_engine.agents.engineer import run_engineer
from ai_engine.agents.janitor import run_janitor
from ai_engine.agents.orchestrator import run_phase1
from ai_engine.agents.storyteller import run_storyteller
from ai_engine.graph.state import GraphState
from ai_engine.llm.base import LLMProvider

# Fallback output directory, used only when a caller does not supply its own.
# Mirrors the LOCAL_PROCESSED_DIR default in .env.example (Section 11.5) and
# the identical fallback constants in janitor.py/engineer.py. Production
# callers (backend/api/analyze.py) resolve the real configured path from
# backend.config.Settings.processed_dir and pass it in explicitly.
_DEFAULT_PROCESSED_DIR = Path("./data/processed")


# ---------------------------------------------------------------------------
# Phase 1 — Upload & Audit
# ---------------------------------------------------------------------------


def build_phase1_app(
    *,
    llm: LLMProvider,
    auditor: Auditor,
) -> Any:
    """
    Compile a Phase 1 LangGraph app bound to this request's llm/auditor.

    Single node "orchestrator" wraps run_phase1(), which performs Steps 1-6
    (file load, header normalisation, LLM domain profiling, contextual zero
    engine, 5-tier anomaly detection, quality scoring). It no longer persists
    to the database itself -- it returns anomaly_report in its result dict,
    and backend/api/analyze.py persists anomalies + session fields after
    this graph returns (2026-07-03 architecture audit, decision log item 7).

    Args:
        llm:     Active LLMProvider instance for this request.
        auditor: Auditor bound to the session being analysed.

    Returns:
        A compiled LangGraph app. Call `await app.ainvoke(state)` with a
        GraphState containing at least session_id, llm_provider, file_path,
        and user_intent.
    """
    graph: StateGraph = StateGraph(GraphState)

    async def _orchestrator_node(state: GraphState) -> dict[str, Any]:
        return await run_phase1(state, llm=llm, auditor=auditor)

    graph.add_node("orchestrator", _orchestrator_node)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Phase 2 — Cleaning, Engineering, EDA
# ---------------------------------------------------------------------------


def build_phase2_app(
    *,
    llm: LLMProvider,
    auditor: Auditor,
    processed_dir: Path | str = _DEFAULT_PROCESSED_DIR,
) -> Any:
    """
    Compile a Phase 2+3 LangGraph app bound to this request's llm/auditor.

    Nodes:
      janitor     — Applies HITL decisions, recalculates quality_score_after,
                    saves the clean CSV to processed_dir. Deterministic,
                    no LLM.
      engineer    — One-hot encoding, log transforms, datetime extraction,
                    interaction terms. Saves the engineered CSV to
                    processed_dir. Deterministic, no LLM.
      storyteller — LLM chart-type/axis selection, builds the EDA portfolio,
                    and sets session status to 'complete' via Auditor.
                    Persisting chart_specs/eda_narrative to the database now
                    happens in backend/api/analyze.py after this graph
                    returns, not inside storyteller itself (2026-07-03
                    architecture audit, decision log item 7).

    Args:
        llm:           Active LLMProvider instance for this request.
        auditor:       Auditor bound to the session being processed.
        processed_dir: Directory to save clean/engineered CSVs into. The
                       caller resolves this from its own config (e.g.
                       backend.config.Settings.processed_dir); defaults to
                       _DEFAULT_PROCESSED_DIR only when the caller does not
                       supply one (mirrors janitor.py/engineer.py fallback).

    Returns:
        A compiled LangGraph app. Call `await app.ainvoke(state)` with a
        GraphState containing at least session_id, llm_provider, df_working,
        anomaly_report, and user_decisions.
    """
    graph: StateGraph = StateGraph(GraphState)

    async def _janitor_node(state: GraphState) -> dict[str, Any]:
        return await run_janitor(state, auditor=auditor, processed_dir=processed_dir)

    async def _engineer_node(state: GraphState) -> dict[str, Any]:
        return await run_engineer(state, auditor=auditor, processed_dir=processed_dir)

    async def _storyteller_node(state: GraphState) -> dict[str, Any]:
        return await run_storyteller(state, llm=llm, auditor=auditor)

    graph.add_node("janitor", _janitor_node)
    graph.add_node("engineer", _engineer_node)
    graph.add_node("storyteller", _storyteller_node)

    graph.set_entry_point("janitor")
    graph.add_edge("janitor", "engineer")
    graph.add_edge("engineer", "storyteller")
    graph.add_edge("storyteller", END)

    return graph.compile()
