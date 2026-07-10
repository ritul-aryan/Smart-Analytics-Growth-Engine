"""
backend/db/sqlite.py

SQLite implementation of DatabaseBackend.

Used for local development.  All data lives in a single file at the path
configured by SQLITE_PATH in .env (default: ./data/mae.db).

Driver: aiosqlite (async SQLite wrapper — no thread-pool overhead).

This implementation also exposes the raw engine and session factory used by
backend/db/session.py so that the FastAPI dependency injection layer does not
need to know which backend is active.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.db.base import DatabaseBackend
from backend.db.models import Base

logger = logging.getLogger(__name__)


class SQLiteBackend(DatabaseBackend):
    """
    Concrete DatabaseBackend backed by SQLite via aiosqlite.

    Instantiated once at startup; the engine and session factory are
    reused for the lifetime of the process.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialise with the filesystem path to the SQLite database file.

        Args:
            db_path: Absolute or relative path, e.g. ``./data/mae.db``.
                     The parent directory is created automatically on
                     :meth:`connect`.
        """
        self._db_path = db_path
        self._url = f"sqlite+aiosqlite:///{db_path}"
        self._engine = create_async_engine(
            self._url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    # ------------------------------------------------------------------
    # DatabaseBackend interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Ensure the database directory exists and create all ORM tables.

        In production, Alembic migrations run first via the FastAPI
        lifespan.  This call is a safety net that ensures the schema
        exists even when migrations are skipped (e.g. fresh dev setup).
        """
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("SQLiteBackend connected — path=%s", self._db_path)

    async def disconnect(self) -> None:
        """Dispose the connection pool and release all file handles."""
        await self._engine.dispose()
        logger.info("SQLiteBackend disconnected — path=%s", self._db_path)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:  # type: ignore[override]
        """
        Async context manager that yields a scoped AsyncSession.

        Commits on clean exit, rolls back on exception.
        """
        async with self._factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                await db.close()

    async def health_check(self) -> bool:
        """Return True if the SQLite file is readable and queryable."""
        try:
            async with self._factory() as db:
                await db.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("SQLiteBackend health_check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Accessors used by backend/db/session.py
    # ------------------------------------------------------------------

    @property
    def engine(self):  # type: ignore[return]
        """Expose the raw AsyncEngine for Alembic and test fixtures."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Expose the session factory for the FastAPI get_db dependency."""
        return self._factory
