"""
backend/main.py

FastAPI application entry point for the MAE (Multi-Agent EDA Engine) backend.

Startup sequence:
  1. Register all API routers
  2. Configure CORS for local Vite dev server (http://localhost:5173)

Alembic migrations are intentionally NOT run here.  They are applied by
start.bat / start.sh via ``alembic upgrade head`` before uvicorn launches.
Running migrations inside the lifespan causes a deadlock: Alembic's env.py
calls asyncio.run() internally, and asyncio.run()'s executor-shutdown phase
hangs when called from within asyncio.to_thread() because aiosqlite's
background threads cannot exit cleanly while nested inside the FastAPI loop.

Run with:  uvicorn backend.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analyze import router as analyze_router
from backend.api.chat import router as chat_router
from backend.api.files import router as files_router
from backend.api.health import router as health_router
from backend.api.sessions import router as sessions_router
from backend.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Log startup/shutdown; migrations are handled by the start scripts."""
    settings = get_settings()
    logger.info("MAE backend starting -- db_backend=%s", settings.db_backend)
    yield
    logger.info("MAE backend shutting down")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="MAE -- Multi-Agent EDA Engine",
        description=(
            "AI-powered data analytics platform for SMEs. "
            "Three-phase pipeline: anomaly detection, HITL review, EDA portfolio."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS -- permit Vite dev server
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    if hasattr(settings, "cors_origins") and settings.cors_origins:
        origins = list(settings.cors_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    # analyze_router registers both POST /api/analyze/start and
    # POST /api/analyze/complete -- both endpoints now live in
    # backend/api/analyze.py per spec Section 4.2 (2026-07-03 merge,
    # decision log item 2). backend/api/complete.py has been retired to
    # junk-unused-dump/.
    app.include_router(analyze_router)
    app.include_router(chat_router)
    app.include_router(files_router)
    app.include_router(health_router)
    app.include_router(sessions_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": "SAGE — Multi-Agent EDA Engine",
            "status": "running",
            "docs": "/api/docs",
        }

    return app


app = create_app()
