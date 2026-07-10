"""
backend/tasks/base.py

TaskQueue abstract interface.

Defines the contract that every concrete task queue backend must fulfil.
Application code enqueues work through this interface so that the local
FastAPI BackgroundTasks implementation can be swapped for ARQ + Redis with
a single config change (TASK_BACKEND=arq).

Current implementations:
  backend/tasks/background.py  — FastAPI BackgroundTasks (local dev)
  backend/tasks/arq.py         — ARQ + Redis (cloud production)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class TaskQueue(ABC):
    """
    Abstract task queue.

    All methods accept a callable plus its positional and keyword arguments.
    Implementations decide whether to execute immediately in the background
    (BackgroundTasks) or push to an external queue (ARQ + Redis).
    """

    @abstractmethod
    async def enqueue(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Schedule ``func(*args, **kwargs)`` for asynchronous execution.

        Args:
            func:   The async callable to execute.
            *args:  Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        The call returns immediately — callers must not assume ``func``
        has completed when ``enqueue`` returns.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Return True if the queue backend is operational.

        For BackgroundTasks this is always True (in-process).
        For ARQ it verifies the Redis connection is alive.
        Must not raise — catch all exceptions and return False.
        """
