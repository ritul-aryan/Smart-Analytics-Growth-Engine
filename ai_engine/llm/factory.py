"""
ai_engine/llm/factory.py

LLM provider factory -- returns the correct LLMProvider for a given
provider string.

Fallback chain for 'gemini-2.0-flash':
    1. GeminiProvider (gemini-2.0-flash)
    2. OllamaProvider  -- automatic fallback when Gemini raises LLMProviderError
       (quota exhausted, network error, missing API key)

The gemini-1.5-flash backup has been removed from the retry chain.
Gemini fails fast on quota errors so the chain switches to Ollama
immediately without waiting for multiple retry attempts.

Provider strings:
    'gemini-2.0-flash'  ->  _ChainProvider(Gemini, Ollama)
    'ollama'            ->  OllamaProvider  (direct, no chain)
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel

from ai_engine.llm.base import LLMProvider, LLMProviderError
from ai_engine.llm.gemini import GeminiProvider
from ai_engine.llm.ollama import OllamaProvider

# Fallback defaults, used only when a caller does not supply its own config.
# Mirrors the .env.example defaults in Section 11.5 of
# MAE_Master_Architecture_v2.docx. Production callers (backend/api/*.py)
# resolve the real values from backend.config.Settings and pass them in
# explicitly -- ai_engine does not import backend directly (2026-07-03
# architecture audit, decision log item 7).
_DEFAULT_PROVIDER = "gemini-2.0-flash"
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

# Module-level cache: one provider instance per provider string per process.
_provider_cache: dict[str, LLMProvider] = {}


# ---------------------------------------------------------------------------
# Chain provider -- primary with automatic fallback to secondary
# ---------------------------------------------------------------------------


class _ChainProvider(LLMProvider):
    """
    Wraps two LLMProvider instances.  Delegates to primary; if primary raises
    LLMProviderError (quota exhausted, unavailable) transparently retries
    with secondary and logs a warning.
    """

    def __init__(self, primary: LLMProvider, secondary: LLMProvider) -> None:
        self._primary = primary
        self._secondary = secondary

    @property
    def name(self) -> str:
        return f"{self._primary.name}+{self._secondary.name}"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "general",
    ) -> str:
        try:
            return await self._primary.complete(prompt, system=system, task=task)
        except LLMProviderError as exc:
            logger.warning(
                "Primary LLM failed (%s) -- falling back to %s: %s",
                self._primary.name, self._secondary.name, exc,
            )
            return await self._secondary.complete(prompt, system=system, task=task)

    async def complete_json(
        self,
        prompt: str,
        schema: type[_T],
        *,
        system: str | None = None,
        task: str = "general",
    ) -> _T:
        try:
            return await self._primary.complete_json(
                prompt, schema, system=system, task=task
            )
        except LLMProviderError as exc:
            logger.warning(
                "Primary LLM failed (%s) -- falling back to %s: %s",
                self._primary.name, self._secondary.name, exc,
            )
            return await self._secondary.complete_json(
                prompt, schema, system=system, task=task
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_llm_provider(
    provider: str | None = None,
    api_key: str | None = None,
    *,
    default_provider: str = _DEFAULT_PROVIDER,
    ollama_base_url: str = _DEFAULT_OLLAMA_BASE_URL,
    gemini_api_key: str | None = None,
) -> LLMProvider:
    """
    Return the LLMProvider instance for the given provider string.

    If provider is None or blank, uses default_provider.

    Args:
        provider:         Optional override. One of: 'gemini-2.0-flash', 'ollama'.
        api_key:          Optional user-supplied (BYOK) key for this request.
                          When provided it overrides gemini_api_key for cloud
                          providers and the instance is built fresh — never
                          cached — so one user's key can never leak into
                          another request. Ignored for Ollama (local, keyless).
        default_provider: Fallback provider string used when `provider` is
                          None or blank. Callers resolve this from their own
                          config (e.g. backend.config.Settings.llm_provider) --
                          ai_engine does not read backend config directly.
        ollama_base_url:  Ollama endpoint. Callers resolve this from their own
                          config (e.g. Settings.ollama_base_url).
        gemini_api_key:   .env-sourced Gemini key, used when `api_key` (the
                          per-request BYOK override) is not supplied. Callers
                          resolve this from their own config
                          (e.g. Settings.gemini_api_key).

    Returns:
        A cached LLMProvider instance (or _ChainProvider for Gemini).
        Uncached when a dynamic api_key is supplied.

    Raises:
        LLMProviderError: If the provider string is not recognised.
    """
    resolved = (provider or default_provider).lower().strip()
    dynamic_key = (api_key or "").strip() or None

    # Dynamic-key instances bypass the cache entirely (cheap to build).
    if dynamic_key is not None:
        instance = _build_provider(resolved, ollama_base_url, gemini_api_key, api_key=dynamic_key)
        logger.info(
            "LLM provider initialised with request-scoped API key: %s",
            instance.name,
        )
        return instance

    if resolved in _provider_cache:
        return _provider_cache[resolved]

    instance = _build_provider(resolved, ollama_base_url, gemini_api_key)
    _provider_cache[resolved] = instance
    logger.info("LLM provider initialised: %s", instance.name)
    return instance


def _build_provider(
    provider: str,
    ollama_base_url: str,
    gemini_api_key: str | None,
    api_key: str | None = None,
) -> LLMProvider:
    ollama = OllamaProvider(base_url=ollama_base_url)

    if provider in ("gemini-2.0-flash", "gemini"):
        # Request-scoped BYOK key takes precedence over the caller-supplied default.
        key = api_key or gemini_api_key
        if not key:
            logger.warning(
                "No Gemini API key (header or default) -- "
                "using Ollama directly (no Gemini chain)"
            )
            return ollama
        gemini = GeminiProvider(api_key=key)
        # Chain: try Gemini first, fall back to Ollama on any LLMProviderError
        return _ChainProvider(gemini, ollama)

    if provider == "ollama":
        return ollama

    raise LLMProviderError(
        provider,
        f"Unknown LLM provider '{provider}'. Valid options: 'gemini-2.0-flash', 'ollama'.",
    )


def clear_provider_cache() -> None:
    """Evict all cached provider instances. For use in tests only."""
    _provider_cache.clear()
    logger.debug("LLM provider cache cleared")
