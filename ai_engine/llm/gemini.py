"""
ai_engine/llm/gemini.py

Gemini LLM provider -- Gemini 2.0 Flash primary model only.

Rate-limit handling (429 / ResourceExhausted):
    Instead of failing immediately, the provider retries up to LLM_MAX_RETRIES
    times with exponential backoff + full jitter:
        wait = min(LLM_RATE_LIMIT_BASE_DELAY * 2^attempt + uniform(0,1), MAX)
    After all retries are exhausted it raises LLMProviderError so the
    _ChainProvider in factory.py can fall back to Ollama.

Non-quota transient errors are retried with the standard LLM_RETRY_DELAY_SECONDS
exponential back-off (no jitter -- these are genuine transient failures, not
thundering-herd quota events).

Concurrency: each ainvoke() call is wrapped in LLM_SEMAPHORE (base.py) to cap
the number of simultaneous API calls across all providers and pipeline agents.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError

from ai_engine.config import (
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_PRIMARY_MODEL,
    GEMINI_TEMPERATURE,
    LLM_MAX_RETRIES,
    LLM_RATE_LIMIT_BASE_DELAY,
    LLM_RATE_LIMIT_MAX_DELAY,
    LLM_RETRY_DELAY_SECONDS,
)
from ai_engine.llm.base import LLM_SEMAPHORE, LLMProvider, LLMProviderError

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

# Exception types that indicate a rate-limit or quota exhaustion.
_RATE_LIMIT_EXCEPTIONS: tuple[type[Exception], ...] = ()
try:
    from google.api_core.exceptions import DeadlineExceeded, ResourceExhausted
    _RATE_LIMIT_EXCEPTIONS = (ResourceExhausted, DeadlineExceeded)
except ImportError:
    pass


def _is_rate_limit(exc: Exception) -> bool:
    """Return True if exc represents a quota or rate-limit error."""
    if _RATE_LIMIT_EXCEPTIONS and isinstance(exc, _RATE_LIMIT_EXCEPTIONS):
        return True
    msg = str(exc).lower()
    return "quota" in msg or "rate" in msg or "429" in msg or "exhausted" in msg


def _rate_limit_wait(attempt: int) -> float:
    """Full-jitter exponential backoff for 429 errors.

    Formula: min(BASE * 2^attempt + uniform(0, 1), MAX)
    Adds randomness so agents hitting the limit simultaneously do not
    all wake up and hammer the API at the same moment.
    """
    return min(
        LLM_RATE_LIMIT_BASE_DELAY * (2 ** attempt) + random.uniform(0.0, 1.0),
        LLM_RATE_LIMIT_MAX_DELAY,
    )


class GeminiProvider(LLMProvider):
    """
    LLM provider backed by Google Gemini via LangChain.

    Instantiate via factory.py -- do not construct directly in agent code.
    """

    def __init__(self, api_key: str) -> None:
        self._model = ChatGoogleGenerativeAI(
            model=GEMINI_PRIMARY_MODEL,
            google_api_key=api_key,
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        )

    @property
    def name(self) -> str:
        return GEMINI_PRIMARY_MODEL

    def _build_messages(
        self, prompt: str, system: str | None
    ) -> list[SystemMessage | HumanMessage]:
        messages: list[SystemMessage | HumanMessage] = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
        return messages

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "general",
    ) -> str:
        """
        Generate a plain-text completion.

        On 429 / ResourceExhausted: backoff with jitter, then retry.
        After LLM_MAX_RETRIES exhausted: raise LLMProviderError so the
        factory chain can fall back to Ollama.
        """
        messages = self._build_messages(prompt, system)
        last_exc: Exception | None = None

        for attempt in range(LLM_MAX_RETRIES):
            try:
                async with LLM_SEMAPHORE:
                    response = await self._model.ainvoke(messages)
                content = str(response.content).strip()
                logger.debug("Gemini complete -- task=%s chars=%d", task, len(content))
                return content
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc):
                    wait = _rate_limit_wait(attempt)
                    logger.warning(
                        "Gemini 429 rate-limit (attempt %d/%d); backing off %.1fs",
                        attempt + 1, LLM_MAX_RETRIES, wait,
                    )
                else:
                    wait = LLM_RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(
                        "Gemini attempt %d/%d failed: %s -- retrying in %.1fs",
                        attempt + 1, LLM_MAX_RETRIES, exc, wait,
                    )
                await asyncio.sleep(wait)

        raise LLMProviderError(
            self.name,
            f"All {LLM_MAX_RETRIES} attempts failed.",
            cause=last_exc,
        )

    async def complete_json(
        self,
        prompt: str,
        schema: type[_T],
        *,
        system: str | None = None,
        task: str = "general",
    ) -> _T:
        """
        Generate a structured completion using Gemini function-calling mode.

        Same retry / backoff policy as complete().
        """
        messages = self._build_messages(prompt, system)
        last_exc: Exception | None = None

        for attempt in range(LLM_MAX_RETRIES):
            try:
                structured = self._model.with_structured_output(schema)
                async with LLM_SEMAPHORE:
                    result = await structured.ainvoke(messages)
                if not isinstance(result, schema):
                    raise TypeError(
                        f"Expected {schema.__name__}, got {type(result).__name__}"
                    )
                logger.debug("Gemini complete_json -- schema=%s", schema.__name__)
                return result  # type: ignore[return-value]
            except ValidationError:
                raise
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc):
                    wait = _rate_limit_wait(attempt)
                    logger.warning(
                        "Gemini JSON 429 rate-limit (attempt %d/%d); backing off %.1fs",
                        attempt + 1, LLM_MAX_RETRIES, wait,
                    )
                else:
                    wait = LLM_RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(
                        "Gemini JSON attempt %d/%d failed: %s -- retrying in %.1fs",
                        attempt + 1, LLM_MAX_RETRIES, exc, wait,
                    )
                await asyncio.sleep(wait)

        raise LLMProviderError(
            self.name,
            f"All {LLM_MAX_RETRIES} JSON attempts failed.",
            cause=last_exc,
        )
