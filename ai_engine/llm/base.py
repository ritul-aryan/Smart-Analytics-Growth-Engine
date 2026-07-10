"""
ai_engine/llm/base.py

Abstract base class for all LLM provider implementations.

Every provider (Gemini, Ollama, and any future addition) must implement
this interface.  No agent or pipeline node may import a concrete provider
directly -- all LLM calls flow through this abstraction.

Adding a new provider requires only:
    1. Creating a new file in ai_engine/llm/
    2. Subclassing LLMProvider
    3. Adding the provider string to factory.py

No other file changes are needed.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from ai_engine.config import LLM_CONCURRENT_CALLS

# TypeVar bound to BaseModel -- used for typed structured completions.
# Each call site substitutes its own Pydantic schema.
_T = TypeVar("_T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Global concurrency throttle
# ---------------------------------------------------------------------------

# Caps the number of LLM calls executing simultaneously across ALL provider
# instances and pipeline stages in the process.  When more than
# LLM_CONCURRENT_CALLS agents reach their ainvoke() concurrently, the extras
# wait here -- naturally staggering requests and preventing 429 storms.
#
# Both GeminiProvider and OllamaProvider acquire this semaphore immediately
# before each ainvoke() call and release it as soon as the call returns
# (or raises).  The backoff sleep between retries happens OUTSIDE the lock
# so other agents can proceed while we wait.
LLM_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(LLM_CONCURRENT_CALLS)


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.

    Concrete implementations must be async-safe.  All methods use
    async/await and may be called from FastAPI route handlers or
    LangGraph nodes without blocking the event loop.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the canonical provider identifier string.

        Must match one of the valid llm_provider values in backend/config.py
        (e.g. 'gemini-2.0-flash', 'gemini-1.5-flash', 'ollama').
        """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "general",
    ) -> str:
        """
        Generate a plain-text completion for the given prompt.

        Args:
            prompt: The user-turn message to send to the LLM.
            system: Optional system instruction prepended to the conversation.
                    If None, the provider uses its default system prompt.
            task:   Hint for providers that route to different models per
                    task type.  Valid values: 'general', 'routing',
                    'normalisation', 'profiling', 'storytelling'.
                    Gemini ignores this; Ollama uses it to select a model.

        Returns:
            The raw text content of the LLM response, stripped of
            surrounding whitespace.

        Raises:
            LLMProviderError: On unrecoverable generation failure after
                              all retry attempts are exhausted.
        """

    @abstractmethod
    async def complete_json(
        self,
        prompt: str,
        schema: type[_T],
        *,
        system: str | None = None,
        task: str = "general",
    ) -> _T:
        """
        Generate a structured completion validated against a Pydantic model.

        The provider instructs the LLM to respond as valid JSON matching
        the supplied schema, then parses and validates the response.

        Args:
            prompt:  The user-turn message describing the structured task.
            schema:  A Pydantic BaseModel subclass that defines the
                     expected response shape and provides validation.
            system:  Optional system instruction.
            task:    Task-routing hint (see complete() for valid values).

        Returns:
            A validated instance of the supplied schema type.

        Raises:
            LLMProviderError:    On generation failure after all retries.
            ValidationError:     If the LLM response cannot be parsed into
                                 the requested schema after all retries.
        """


class LLMProviderError(Exception):
    """
    Raised when an LLM provider fails after exhausting all retry attempts.

    Wraps the underlying exception so callers can catch this single type
    regardless of which provider is active.
    """

    def __init__(self, provider: str, message: str, cause: Exception | None = None) -> None:
        """
        Initialise with provider name, message, and optional root cause.

        Args:
            provider: Provider name (e.g. 'gemini-2.0-flash').
            message:  Human-readable description of the failure.
            cause:    The underlying exception, if any.
        """
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.cause = cause
