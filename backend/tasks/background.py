"""
backend/tasks/background.py

FastAPI BackgroundTasks implementation of TaskQueue.

Used for local development.  Tasks run in the same process as the web
server, after the HTTP response has been sent to the client.  No external
broker is required.

Limitation: tasks are lost if the server process is killed before they
complete.  Acceptable for local dev; use ARQ + Redis for production.

Activation: TASK_BACKEND=background in .env (this is the default).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from backend.tasks.base import TaskQueue

logger = logging.getLogger(__name__)


class BackgroundTaskQueue(TaskQueue):
    """
    TaskQueue backed by asyncio.create_task.

    Wraps the callable in a fire-and-forget coroutine so that the
    FastAPI endpoint can return immediately while the task runs
    concurrently in the same event loop.

    In route handlers that have access to FastAPI's BackgroundTasks
    object, prefer passing it via the constructor so FastAPI can manage
    the task lifecycle.  When no BackgroundTasks object is available
    (e.g. in tests or standalone scripts), tasks run via asyncio directly.
    """

    def __init__(self, background_tasks: Any | None = None) -> None:
        """
        Args:
            background_tasks: Optional FastAPI ``BackgroundTasks`` instance.
                If supplied, tasks are registered with FastAPI.
                If None, tasks are launched via ``asyncio.create_task``.
        """
        self._background_tasks = background_tasks

    async def enqueue(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Schedule ``func`` for background execution."""
        if self._background_tasks is not None:
            self._background_tasks.add_task(func, *args, **kwargs)
            logger.debug("Task enqueued via FastAPI BackgroundTasks: %s", func.__name__)
        else:
            asyncio.create_task(_run(func, *args, **kwargs))
            logger.debug("Task enqueued via asyncio.create_task: %s", func.__name__)

    async def health_check(self) -> bool:
        """Always healthy — tasks run in-process with no external dependency."""
        return True


async def _run(func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> None:
    """Wrapper that logs exceptions from fire-and-forget tasks."""
    try:
        await func(*args, **kwargs)
    except Exception as exc:
        logger.error("Background task %s failed: %s", func.__name__, exc, exc_info=True)
