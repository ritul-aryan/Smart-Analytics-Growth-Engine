"""
ai_engine/llm/ollama.py

Ollama LLM provider -- fully offline, no API key required.

Routes to different local models based on the task type:
    routing / normalisation / general  ->  qwen2.5-coder:7b
    profiling / storytelling / narrative ->  llama3.1:8b

Structured output uses JSON mode, which instructs Ollama to constrain
generation to valid JSON.  The response is then parsed and validated
against the caller-supplied Pydantic schema.

Empty-response guard: if Ollama returns an empty string (e.g. during a
model cold-start or under high memory pressure), the raw content is
checked BEFORE json.loads() is called.  A ValueError is raised so the
retry loop handles it cleanly instead of surfacing a JSONDecodeError at
"char 0" to the caller.

Concurrency: each ainvoke() call is wrapped in LLM_SEMAPHORE (base.py)
to cap simultaneous calls across all providers and pipeline agents.

The Ollama server must be running locally at OLLAMA_BASE_URL (default:
http://localhost:11434).  Start it with: ollama serve
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

from ai_engine.config import (
    LLM_MAX_RETRIES,
    LLM_RETRY_DELAY_SECONDS,
    OLLAMA_MAX_TOKENS,
    OLLAMA_ROUTER_MODEL,
    OLLAMA_ROUTER_TASKS,
    OLLAMA_STORYTELLER_MODEL,
    OLLAMA_STORYTELLER_TASKS,
    OLLAMA_TEMPERATURE,
)
from ai_engine.llm.base import LLM_SEMAPHORE, LLMProvider, LLMProviderError

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

_JSON_SYSTEM_SUFFIX = (
    "\n\nIMPORTANT: Respond ONLY with a valid JSON object. "
    "No markdown fences, no explanation, no extra text."
)


class OllamaProvider(LLMProvider):
    """
    LLM provider backed by a local Ollama server.

    Instantiate via factory.py -- do not construct directly in agent code.
    """

    def __init__(self, base_url: str) -> None:
        """
        Initialise router and storyteller model instances.

        Args:
            base_url: Ollama server base URL (e.g. 'http://localhost:11434').
        """
        self._base_url = base_url
        self._router_model = ChatOllama(
            model=OLLAMA_ROUTER_MODEL,
            base_url=base_url,
            temperature=OLLAMA_TEMPERATURE,
            num_predict=OLLAMA_MAX_TOKENS,
        )
        self._storyteller_model = ChatOllama(
            model=OLLAMA_STORYTELLER_MODEL,
            base_url=base_url,
            temperature=OLLAMA_TEMPERATURE,
            num_predict=OLLAMA_MAX_TOKENS,
        )

    @property
    def name(self) -> str:
        """Return the provider identifier string."""
        return "ollama"

    def _select_model(self, task: str) -> ChatOllama:
        """Return the correct Ollama model instance for the given task."""
        if task in OLLAMA_STORYTELLER_TASKS:
            return self._storyteller_model
        return self._router_model

    def _build_messages(
        self, prompt: str, system: str | None
    ) -> list[SystemMessage | HumanMessage]:
        """Construct the LangChain message list."""
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
        Generate a plain-text completion using the task-appropriate local model.

        Args:
            prompt: User-turn message.
            system: Optional system instruction.
            task:   Routes to qwen2.5-coder (routing/general) or
                    llama3.1 (storytelling/profiling).
        """
        model = self._select_model(task)
        messages = self._build_messages(prompt, system)
        last_exc: Exception | None = None

        for attempt in range(LLM_MAX_RETRIES):
            try:
                async with LLM_SEMAPHORE:
                    response = await model.ainvoke(messages)
                content = str(response.content).strip()
                if not content:
                    raise ValueError(
                        f"Ollama ({model.model}) returned an empty response for task={task!r}"
                    )
                logger.debug(
                    "Ollama complete -- model=%s task=%s chars=%d",
                    model.model, task, len(content),
                )
                return content
            except Exception as exc:
                last_exc = exc
                wait = LLM_RETRY_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    "Ollama attempt %d/%d failed: %s -- retrying in %.1fs",
                    attempt + 1, LLM_MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)

        raise LLMProviderError(
            self.name,
            f"All {LLM_MAX_RETRIES} attempts failed. Is Ollama running at {self._base_url}?",
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
        Generate a structured completion using Ollama JSON mode.

        Appends a strict JSON-only instruction to the system prompt, then
        parses the raw response text as JSON and validates it against the
        Pydantic schema.

        Empty-response guard: checks for an empty string before calling
        json.loads() to prevent JSONDecodeError at char 0 from propagating
        to the caller.  An empty or fence-only response is treated as a
        retryable failure.
        """
        model = self._select_model(task)
        json_system = (system or "") + _JSON_SYSTEM_SUFFIX
        schema_hint = f"\n\nExpected JSON schema:\n{json.dumps(schema.model_json_schema(), indent=2)}"
        messages = self._build_messages(prompt + schema_hint, json_system)
        last_exc: Exception | None = None

        for attempt in range(LLM_MAX_RETRIES):
            try:
                async with LLM_SEMAPHORE:
                    response = await model.ainvoke(messages)
                raw = str(response.content).strip()

                if not raw:
                    raise ValueError(
                        f"Ollama ({model.model}) returned an empty response "
                        f"for schema={schema.__name__!r}"
                    )

                # Strip markdown code fences if the model adds them anyway
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                if not raw:
                    raise ValueError(
                        f"Ollama ({model.model}) response was empty after "
                        f"stripping code fences (schema={schema.__name__!r})"
                    )

                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as json_exc:
                    raise ValueError(
                        f"Ollama JSON decode failed at char {json_exc.pos} "
                        f"({json_exc.msg!r}). Raw (first 120 chars): {raw[:120]!r}"
                    ) from json_exc

                result = schema.model_validate(parsed)
                logger.debug(
                    "Ollama complete_json -- model=%s schema=%s",
                    model.model, schema.__name__,
                )
                return result

            except ValidationError:
                raise  # Schema mismatch -- no point retrying with same model
            except Exception as exc:
                last_exc = exc
                wait = LLM_RETRY_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    "Ollama JSON attempt %d/%d failed: %s -- retrying in %.1fs",
                    attempt + 1, LLM_MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)

        raise LLMProviderError(
            self.name,
            f"All {LLM_MAX_RETRIES} JSON attempts failed.",
            cause=last_exc,
        )
