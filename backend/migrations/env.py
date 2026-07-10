"""
backend/migrations/env.py

Alembic migration environment — async-compatible configuration.

Supports both offline mode (generates SQL without a live DB connection)
and online mode (connects to the live DB and runs migrations directly).
The database URL is always sourced from backend.config.get_settings()
so that the same .env file drives both the application and migrations.

Run from the project root:
    alembic upgrade head       # apply all pending migrations
    alembic downgrade -1       # roll back one migration
    alembic revision --autogenerate -m "description"  # generate new migration
"""
from __future__ import annotations

import sys
import os

# Automatically adds the root SAGE directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import get_settings
from backend.db.models import Base

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to alembic.ini values
# ---------------------------------------------------------------------------

config = context.config

# Apply the logging config from alembic.ini (sets up sqlalchemy/alembic loggers)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ---------------------------------------------------------------------------
# Target metadata — tells Alembic which schema to compare against
# ---------------------------------------------------------------------------

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Database URL — always from Settings, never from alembic.ini
# ---------------------------------------------------------------------------

settings = get_settings()
_database_url: str = settings.active_database_url


# ---------------------------------------------------------------------------
# Offline migration (generates SQL script without a live DB connection)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode.

    Renders migration SQL to stdout or a file without requiring a live
    database connection.  Useful for generating SQL to review or apply
    manually in production.
    """
    context.configure(
        url=_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

    logger.info("Offline migrations rendered for URL: %s", _database_url)


# ---------------------------------------------------------------------------
# Online migration (connects to live DB and runs migrations directly)
# ---------------------------------------------------------------------------


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    """
    Execute pending migrations against an open database connection.

    Called from within the async engine context.  The `connection` argument
    is a synchronous-wrapped connection provided by `run_sync`.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Render RETURNING clauses for PostgreSQL batch operations
        render_as_batch=(settings.db_backend == "sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in online mode using an async engine.

    Creates a dedicated engine (separate from the application engine) so
    that Alembic has full control over the connection lifecycle.
    """
    connectable = create_async_engine(
        _database_url,
        echo=False,  # Suppress SQL echo during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()
    logger.info("Online migrations complete against: %s", settings.db_backend)


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this module at the top level
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())