"""
backend/api/health.py

Health check endpoint — GET /health.

Per Section 4.2 (directory tree: "api/health.py — GET /health") and
Section 9.1 (API reference: "GET /health | Health check.") of
MAE_Master_Architecture_v2.docx, this lives in its own file and is mounted
at the bare /health path, with no /api prefix.

Previously this check was inlined directly in backend/main.py and mounted
at /api/health instead — a double deviation (wrong file, wrong route) flagged
in the 2026-07-03 architecture audit (decision log item 4). No frontend code
referenced the old /api/health path, so moving it is non-breaking.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])

# Kept as a simple literal rather than a config constant — this is an app
# identity string, not an algorithmic threshold, so it doesn't fall under
# the "no magic numbers" rule in Section 11.1. Matches the FastAPI app
# version declared in backend/main.py's create_app().
_APP_VERSION = "0.1.0"


@router.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    """Liveness check for uptime monitoring. No DB or LLM calls."""
    return {"status": "ok", "version": _APP_VERSION}
