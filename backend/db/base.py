"""
backend/db/base.py

DatabaseBackend abstract interface.

Defines the contract that every concrete database backend (SQLite, PostgreSQL)
must fulfil.  Application code never imports SQLAlchemy engine internals
directly — it works through this interface so that swapping the backing store
is a one-line config change.

Current implementations:
  backend/db/sqlite.py    — local development (SQLite + aiosqlite)
  backend/db/postgres.py  — cloud production (PostgreSQL + asyncpg)

Usage:
    from backend.db.base import DatabaseBackend
    # Concrete instances are obtained via backend.db.session, not directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession


class DatabaseBackend(ABC):
    """
    Abstract database backend.

    Provides engine lifecycle management and session factory methods.
    Implementations must be safe for concurrent async use.
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Initialise the connection pool / engine.

        Called once at application startup.  Implementations should
        run Alembic migrations or create tables here if appropriate.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Dispose of the connection pool / engine.

        Called once at application shutdown.  Must release all
        held connections back to the OS.
        """

    @abstractmethod
    def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async context manager that yields a database session.

        The caller is responsible for committing or rolling back.
        The default FastAPI dependency (get_db) uses this method.

        Example::

            async with backend.session() as db:
                result = await db.execute(select(Session))
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Return True if the database is reachable, False otherwise.

        Used by the GET /health endpoint to surface DB connectivity.
        Must not raise — catch all exceptions internally and return False.
        """
