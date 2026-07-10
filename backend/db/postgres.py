"""
backend/db/postgres.py

PostgreSQL implementation of DatabaseBackend.

Used for cloud / production deployment.  Connection details come from
DATABASE_URL in .env (format: postgresql+asyncpg://user:pass@host:port/db).

Driver: asyncpg — high-performance async PostgreSQL driver.

To activate: set DB_BACKEND=postgres in .env and ensure DATABASE_URL points
at a running PostgreSQL instance.  Then run:

    alembic upgrade head

No application code needs to change — the backend swap is transparent.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.db.base import DatabaseBackend
from backend.db.models import Base

logger = logging.getLogger(__name__)


class PostgreSQLBackend(DatabaseBackend):
    """
    Concrete DatabaseBackend backed by PostgreSQL via asyncpg.

    Uses a connection pool (pool_size=5, max_overflow=10 by default) and
    pool_pre_ping to recover from stale connections after network blips.
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        echo: bool = False,
    ) -> None:
        """
        Initialise with a PostgreSQL async SQLAlchemy URL.

        Args:
            database_url: Must use the ``postgresql+asyncpg://`` scheme.
            pool_size:    Number of persistent connections in the pool.
            max_overflow: Additional connections allowed beyond pool_size.
            echo:         Log all SQL statements (development only).
        """
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "PostgreSQLBackend requires a postgresql+asyncpg:// URL. "
                f"Got: {database_url!r}"
            )

        self._url = database_url
        self._engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,       # Discard stale connections silently
            pool_recycle=1800,        # Recycle connections after 30 minutes
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
        Verify connectivity and log confirmation.

        Does NOT run Alembic migrations — that is handled by the FastAPI
        lifespan hook in backend/main.py.  This method simply confirms
        the database is reachable so startup fails fast on misconfiguration.
        """
        async with self._factory() as db:
            await db.execute(text("SELECT 1"))
        logger.info("PostgreSQLBackend connected — url=%s", self._redacted_url)

    async def disconnect(self) -> None:
        """Dispose all pooled connections and release resources."""
        await self._engine.dispose()
        logger.info("PostgreSQLBackend disconnected — url=%s", self._redacted_url)

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
        """Return True if PostgreSQL is reachable and accepting queries."""
        try:
            async with self._factory() as db:
                await db.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("PostgreSQLBackend health_check failed: %s", exc)
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _redacted_url(self) -> str:
        """Return the URL with the password replaced by *** for safe logging."""
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(self._url)
            if parsed.password:
                netloc = parsed.netloc.replace(parsed.password, "***")
                return urlunparse(parsed._replace(netloc=netloc))
        except Exception:
            pass
        return "<redacted>"
