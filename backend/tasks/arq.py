"""
backend/tasks/arq.py

ARQ + Redis implementation of TaskQueue.

Used for cloud / production deployment.  Tasks are serialised and pushed
to a Redis queue; a separate ARQ worker process picks them up and executes
them.  This decouples task execution from the web server process and
survives server restarts.

Prerequisites:
  1. Redis running and reachable at REDIS_URL.
  2. ARQ worker started: ``arq backend.tasks.arq.WorkerSettings``

Activation: TASK_BACKEND=arq in .env.

Note: ARQ is an optional dependency.  Import errors are deferred to
runtime so that the application can start without ARQ installed when
TASK_BACKEND=background (the default).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.tasks.base import TaskQueue

logger = logging.getLogger(__name__)


class ArqTaskQueue(TaskQueue):
    """
    TaskQueue backed by ARQ + Redis.

    Pushes tasks to Redis via arq.create_pool.  The ARQ worker must be
    running separately to consume and execute queued tasks.
    """

    def __init__(self, redis_url: str) -> None:
        """
        Args:
            redis_url: Redis connection string, e.g. ``redis://localhost:6379``.
        """
        self._redis_url = redis_url
        self._pool: Any = None  # arq.ArqRedis, lazily initialised

    async def _get_pool(self) -> Any:
        """Return (or create) the ARQ Redis connection pool."""
        if self._pool is None:
            try:
                import arq  # type: ignore[import]
                self._pool = await arq.create_pool(
                    arq.connections.RedisSettings.from_dsn(self._redis_url)
                )
                logger.info("ARQ pool connected — url=%s", self._redis_url)
            except ImportError as exc:
                raise RuntimeError(
                    "arq is not installed. "
                    "Add 'arq' to requirements.txt or switch TASK_BACKEND=background."
                ) from exc
        return self._pool

    async def enqueue(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Push the task to Redis for the ARQ worker to execute."""
        pool = await self._get_pool()
        job = await pool.enqueue_job(func.__name__, *args, **kwargs)
        logger.debug(
            "Task enqueued via ARQ — func=%s job_id=%s",
            func.__name__,
            getattr(job, "job_id", "unknown"),
        )

    async def health_check(self) -> bool:
        """Return True if Redis is reachable via the ARQ pool."""
        try:
            pool = await self._get_pool()
            await pool.ping()
            return True
        except Exception as exc:
            logger.warning("ArqTaskQueue health_check failed: %s", exc)
            return False

    async def close(self) -> None:
        """Close the Redis connection pool on application shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("ARQ pool closed")


# ---------------------------------------------------------------------------
# ARQ WorkerSettings — used when launching the worker process
# ---------------------------------------------------------------------------

class WorkerSettings:
    """
    ARQ worker configuration.

    Start the worker with:
        arq backend.tasks.arq.WorkerSettings

    Add task functions to ``functions`` as the application grows.
    """

    redis_settings = None  # Populated lazily by build()

    functions: list[Any] = []  # Register task callables here

    @classmethod
    def build(cls) -> "WorkerSettings":
        """Populate redis_settings from the active config.

        Called explicitly rather than at class-definition time so that
        importing this module never triggers get_settings() — which
        would fail if .env is absent (e.g. during test collection).
        """
        from backend.config import get_settings  # deferred import
        settings = get_settings()
        try:
            import arq  # type: ignore[import]
            cls.redis_settings = arq.connections.RedisSettings.from_dsn(
                settings.redis_url
            )
        except ImportError:
            pass
        return cls
