"""
backend/db/session.py

Async SQLAlchemy engine, session factory, and FastAPI dependency injection.

All database access in MAE flows through the `get_db` dependency -- no
module may construct a Session directly.  The engine and session factory
are built once at import time from the frozen Settings instance.

Supports both backends transparently:
  - SQLite  (local dev)  -- via aiosqlite driver
  - PostgreSQL (cloud)   -- via asyncpg driver

Switching backends is a single .env change (DB_BACKEND=postgres); no code
in this file changes.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import get_settings
from backend.db.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

settings = get_settings()

_connect_args: dict[str, object] = {}
_pool_kwargs: dict[str, object] = {}

# SQLite with aiosqlite:
#   - check_same_thread=False  -- required because aiosqlite uses a background
#     thread for every connection; without this SQLite rejects cross-thread use.
#   - StaticPool               -- forces all async sessions to share a single
#     underlying SQLite connection, serialising writes and eliminating the
#     "database is locked" / PendingRollbackError that occurs when the
#     background Phase-1 task and an incoming API request write concurrently.
if settings.db_backend == "sqlite":
    _connect_args = {"check_same_thread": False}
    _pool_kwargs = {"poolclass": StaticPool}

engine: AsyncEngine = create_async_engine(
    settings.active_database_url,
    echo=(settings.app_env == "development"),
    pool_pre_ping=(settings.db_backend == "postgres"),
    connect_args=_connect_args,
    **_pool_kwargs,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession for use as a FastAPI dependency.

    Commits on clean exit, rolls back on any unhandled exception, and
    always closes the session.  Inject into route handlers with:

        async def my_route(db: DbSession) -> ...:

    where DbSession is the type alias defined below.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Convenience type alias -- use `DbSession` as the parameter type in routes
# instead of the verbose `Annotated[AsyncSession, Depends(get_db)]`.
DbSession = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """
    Create all tables from the ORM metadata if they do not already exist.

    Called at application startup (via FastAPI lifespan) and in the test
    suite conftest.  In production, Alembic migrations take precedence --
    this function is a safety net for local dev and in-memory test DBs.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created via init_db()")


async def drop_db() -> None:
    """
    Drop all tables.

    Used exclusively in the test suite (with an in-memory SQLite DB) to
    guarantee a clean slate between test runs.  Never call this in
    production code.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("All database tables dropped via drop_db() -- test use only")


async def get_raw_connection() -> AsyncGenerator[AsyncConnection, None]:
    """
    Yield a raw AsyncConnection for operations that bypass the ORM.

    Used by Alembic's env.py for online migrations and by the test suite
    for bulk fixture insertion.  Prefer get_db() for all normal queries.
    """
    async with engine.connect() as conn:
        yield conn
