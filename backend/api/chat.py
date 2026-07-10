"""
backend/api/chat.py

Conversational Q&A endpoint — POST /api/chat.

Accepts a user message about the active session's dataset and returns an
LLM-generated assistant reply.  History persists in the chat_messages table
so conversation context survives page refresh (fixes prototype Limitation L17).

If the user's message looks like a chart request (contains keywords such as
"show", "plot", "chart", "visualise"), the endpoint calls the LLM for a
Plotly spec, validates the column names against the session's stored
metadata, persists the chart to the charts table, and links it to the
assistant's reply message.

LLM context is the session's metadata_summary — a compact string built in
Phase 1 by the orchestrator that describes the dataset without sending raw
data to the LLM.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from ai_engine.llm.factory import get_llm_provider
from backend.config import get_settings
from backend.db.models import Chart, ChatMessage, MessageRole, Session
from backend.db.session import DbSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

_CHART_KEYWORDS: frozenset[str] = frozenset({
    "show", "plot", "chart", "graph", "visualise", "visualize",
    "histogram", "scatter", "bar", "box", "heatmap", "distribution",
})


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    has_chart: bool
    chart_id: str | None
    timestamp: str


class ChartSpecOut(BaseModel):
    id: str
    session_id: str
    chart_type: str
    title: str
    plotly_config: dict[str, Any]
    insight_text: str
    columns_used: list[str]
    is_custom: bool
    custom_prompt: str | None
    display_order: int


class ChatResponse(BaseModel):
    message: ChatMessageOut
    chart: ChartSpecOut | None = None


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message and receive an AI reply about the dataset",
)
async def chat(body: ChatRequest, db: DbSession) -> ChatResponse:
    """
    Handle one conversational turn.

    1. Load the session (validates it exists).
    2. Persist the user message.
    3. Build context from history + metadata_summary.
    4. Call the LLM.
    5. If chart-request detected, attempt Plotly spec generation.
    6. Persist the assistant reply (with optional chart link).
    7. Return the reply and optional chart.
    """
    try:
        session_uuid = uuid.UUID(body.session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_row: Session | None = await db.get(Session, session_uuid)
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # --- Load recent history (last 10 turns) ---
    history_rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_uuid)
            .order_by(ChatMessage.timestamp.desc())
            .limit(10)
        )
    ).scalars().all()
    history = list(reversed(history_rows))

    # --- Persist user message ---
    user_msg = ChatMessage(
        session_id=session_uuid,
        role=MessageRole.USER,
        content=body.message,
        has_chart=False,
    )
    db.add(user_msg)
    await db.flush()

    # --- Determine request type and call LLM ---
    # ai_engine/llm/factory.py no longer reads backend.config itself (2026-07-03
    # architecture audit, decision log item 7), so the real .env-configured
    # values are resolved here and passed in explicitly.
    settings = get_settings()
    llm = get_llm_provider(
        session_row.llm_provider or "gemini-2.0-flash",
        default_provider=settings.llm_provider,
        ollama_base_url=settings.ollama_base_url,
        gemini_api_key=settings.gemini_api_key,
    )
    meta = session_row.metadata_summary or "(no metadata available)"
    history_text = "\n".join(
        f"{m.role.value.upper()}: {m.content}" for m in history[-6:]
    )
    is_chart_request = _looks_like_chart_request(body.message)

    if is_chart_request:
        reply_text, chart_row = await _handle_chart_request(
            body.message, meta, session_row, db, llm
        )
    else:
        reply_text = await _handle_text_request(body.message, meta, history_text, llm)
        chart_row = None

    # --- Persist assistant reply ---
    assistant_msg = ChatMessage(
        session_id=session_uuid,
        role=MessageRole.ASSISTANT,
        content=reply_text,
        has_chart=chart_row is not None,
        chart_id=chart_row.id if chart_row else None,
    )
    db.add(assistant_msg)
    await db.flush()

    return ChatResponse(
        message=_msg_out(assistant_msg),
        chart=_chart_out(chart_row, body.session_id) if chart_row else None,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _looks_like_chart_request(message: str) -> bool:
    """Return True if the message likely requests a visualisation."""
    lower = message.lower()
    return any(kw in lower for kw in _CHART_KEYWORDS)


async def _handle_text_request(
    message: str,
    meta: str,
    history_text: str,
    llm: Any,
) -> str:
    """Generate a plain-text answer using metadata context."""
    prompt = (
        f"You are an expert data analyst assistant. "
        f"Answer questions about the dataset described below.\n\n"
        f"DATASET SUMMARY:\n{meta}\n\n"
        f"CONVERSATION HISTORY:\n{history_text}\n\n"
        f"USER: {message}\n\n"
        f"Respond concisely in 2-4 sentences. "
        f"Do not make up statistics not in the summary."
    )
    try:
        return await llm.complete(prompt, task="chat")
    except Exception as exc:
        logger.warning("LLM chat failed: %s", exc)
        return (
            "I couldn't generate a response right now. "
            "Please try again or check your LLM provider settings."
        )


async def _handle_chart_request(
    message: str,
    meta: str,
    session_row: Session,
    db: DbSession,
    llm: Any,
) -> tuple[str, Chart | None]:
    """Attempt to generate a Plotly chart spec; return (reply_text, Chart | None)."""
    prompt = (
        f"Generate a Plotly chart spec as JSON for this request.\n\n"
        f"DATASET SUMMARY:\n{meta}\n\n"
        f"USER REQUEST: {message}\n\n"
        f"Return ONLY valid JSON with these keys:\n"
        f"  chart_type: string (histogram|scatter|bar|box|heatmap|line)\n"
        f"  title: string\n"
        f"  x_column: string or null\n"
        f"  y_column: string or null\n"
        f"  color_column: string or null\n"
        f"  insight: string (1 sentence)\n"
        f"Use only column names mentioned in the dataset summary."
    )
    try:
        raw = await llm.complete(prompt, task="chart")
        spec = _parse_json_response(raw)
        if not spec or "chart_type" not in spec:
            raise ValueError("Invalid spec")

        columns_used = [
            c for c in [
                spec.get("x_column"),
                spec.get("y_column"),
                spec.get("color_column"),
            ]
            if c
        ]

        plotly_config: dict[str, Any] = {
            "data": [{
                "type": spec.get("chart_type", "scatter"),
                "x": spec.get("x_column"),
                "y": spec.get("y_column"),
            }],
            "layout": {"title": spec.get("title", "Custom Chart")},
        }

        existing_count = len(
            (await db.execute(
                select(Chart).where(Chart.session_id == session_row.id)
            )).scalars().all()
        )

        chart_row = Chart(
            session_id=session_row.id,
            chart_type=spec.get("chart_type", "scatter"),
            title=spec.get("title", "Custom Chart"),
            plotly_config=plotly_config,
            insight_text=spec.get("insight", ""),
            columns_used=columns_used,
            is_custom=True,
            custom_prompt=message,
            display_order=existing_count,
        )
        db.add(chart_row)
        await db.flush()

        reply_text = (
            f"Here's your chart: **{chart_row.title}**. "
            f"{spec.get('insight', '')}"
        )
        return reply_text, chart_row

    except Exception as exc:
        logger.warning("Chart generation failed for chat request: %s", exc)
        text = await _handle_text_request(message, meta, "", llm)
        return text, None


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response string."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


def _msg_out(msg: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=str(msg.id),
        session_id=str(msg.session_id),
        role=msg.role.value,
        content=msg.content,
        has_chart=msg.has_chart,
        chart_id=str(msg.chart_id) if msg.chart_id else None,
        timestamp=msg.timestamp.isoformat(),
    )


def _chart_out(chart: Chart, session_id: str) -> ChartSpecOut:
    return ChartSpecOut(
        id=str(chart.id),
        session_id=session_id,
        chart_type=chart.chart_type,
        title=chart.title,
        plotly_config=chart.plotly_config,
        insight_text=chart.insight_text,
        columns_used=chart.columns_used,
        is_custom=chart.is_custom,
        custom_prompt=chart.custom_prompt,
        display_order=chart.display_order,
    )
