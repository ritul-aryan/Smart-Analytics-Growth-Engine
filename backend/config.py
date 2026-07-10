"""
backend/config.py

Single source of truth for all MAE backend configuration.

Loads every setting from environment variables (via .env file).
The Settings instance is frozen — no field may be mutated at runtime.
All other modules must import `get_settings()` and never read os.environ
directly.

Usage:
    from backend.config import get_settings
    settings = get_settings()
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API contract constants
# ---------------------------------------------------------------------------

# HTTP header used by the frontend to pass a user-supplied (BYOK) LLM API
# key with an analysis request. The key overrides the .env default for that
# request only and is never persisted or logged.
# Mirrored in frontend/src/api/analyze.ts — keep the two in sync.
LLM_API_KEY_HEADER = "X-LLM-API-Key"


class Settings(BaseSettings):
    """
    Frozen application settings loaded from environment variables.

    All fields map 1-to-1 to the variables documented in .env.example.
    Switching deployment targets (SQLite → PostgreSQL, local → S3, etc.)
    is a config change here — never a code change.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,           # Immutable after construction
        extra="ignore",        # Silently ignore unknown env vars
        case_sensitive=False,  # LLM_PROVIDER and llm_provider both work
    )

    # ------------------------------------------------------------------
    # LLM Configuration
    # ------------------------------------------------------------------

    llm_provider: Literal["gemini-2.0-flash", "gemini-1.5-flash", "ollama"] = Field(
        default="gemini-2.0-flash",
        description="Active LLM provider. Switchable from the UI per-session.",
    )

    gemini_api_key: str = Field(
        default="",
        description="Google AI Studio API key. Required when llm_provider is gemini-*.",
    )

    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the local Ollama server.",
    )

    ollama_router_model: str = Field(
        default="qwen2.5-coder:7b",
        description="Ollama model used for routing and header normalisation.",
    )

    ollama_storyteller_model: str = Field(
        default="llama3.1:8b",
        description="Ollama model used for narrative generation and chart spec.",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    db_backend: Literal["sqlite", "postgres"] = Field(
        default="sqlite",
        description="Active database backend. 'sqlite' for local dev, 'postgres' for cloud.",
    )

    sqlite_path: str = Field(
        default="./data/mae.db",
        description="Filesystem path for the SQLite database file.",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://user:pass@localhost:5432/mae",
        description="Async SQLAlchemy URL used when db_backend=postgres.",
    )

    # ------------------------------------------------------------------
    # Task Queue
    # ------------------------------------------------------------------

    task_backend: Literal["background", "arq"] = Field(
        default="background",
        description="'background' uses FastAPI BackgroundTasks (local). 'arq' uses ARQ + Redis (cloud).",
    )

    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL. Required when task_backend=arq.",
    )

    # ------------------------------------------------------------------
    # File Storage
    # ------------------------------------------------------------------

    storage_backend: Literal["local", "s3"] = Field(
        default="local",
        description="'local' stores files on disk. 's3' targets AWS S3 (cloud).",
    )

    local_upload_dir: str = Field(
        default="./data/uploads",
        description="Directory for raw uploaded files when storage_backend=local.",
    )

    local_processed_dir: str = Field(
        default="./data/processed",
        description="Directory for cleaned and engineered CSVs when storage_backend=local.",
    )

    aws_bucket_name: str = Field(
        default="",
        description="S3 bucket name. Required when storage_backend=s3.",
    )

    aws_access_key_id: str = Field(
        default="",
        description="AWS access key ID. Required when storage_backend=s3.",
    )

    aws_secret_access_key: str = Field(
        default="",
        description="AWS secret access key. Required when storage_backend=s3.",
    )

    # ------------------------------------------------------------------
    # Code Sandbox
    # ------------------------------------------------------------------

    sandbox_backend: Literal["restricted", "docker"] = Field(
        default="restricted",
        description="'restricted' uses RestrictedPython + AST whitelist (local). 'docker' uses isolated containers (cloud).",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    app_env: Literal["development", "production"] = Field(
        default="development",
        description="Runtime environment. Controls debug behaviour and log verbosity.",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Python logging level for the application.",
    )

    max_upload_size_mb: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum permitted upload file size in megabytes.",
    )

    row_limit_soft_warning: int = Field(
        default=50_000,
        ge=1,
        description=(
            "Row count above which the orchestrator emits a soft warning. "
            "Not a hard cutoff — processing continues."
        ),
    )

    # ------------------------------------------------------------------
    # Derived helpers (not environment variables)
    # ------------------------------------------------------------------

    @property
    def sqlite_url(self) -> str:
        """Return the async SQLAlchemy URL for SQLite, derived from sqlite_path."""
        return f"sqlite+aiosqlite:///{self.sqlite_path}"

    @property
    def active_database_url(self) -> str:
        """Return the correct async database URL for the active db_backend."""
        if self.db_backend == "sqlite":
            return self.sqlite_url
        return self.database_url

    @property
    def upload_dir(self) -> Path:
        """Return the local upload directory as a resolved Path object."""
        return Path(self.local_upload_dir).resolve()

    @property
    def processed_dir(self) -> Path:
        """Return the local processed directory as a resolved Path object."""
        return Path(self.local_processed_dir).resolve()

    @property
    def max_upload_size_bytes(self) -> int:
        """Return max_upload_size_mb converted to bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> "Settings":
        """
        Warn loudly at startup if a provider is selected but its
        required credentials are missing. Raises ValueError in production
        so a misconfigured deploy fails fast rather than silently.
        """
        if self.llm_provider.startswith("gemini") and not self.gemini_api_key:
            msg = "GEMINI_API_KEY is required when LLM_PROVIDER is gemini-*."
            if self.app_env == "production":
                raise ValueError(msg)
            logger.warning(msg)

        if self.task_backend == "arq" and not self.redis_url:
            msg = "REDIS_URL is required when TASK_BACKEND=arq."
            if self.app_env == "production":
                raise ValueError(msg)
            logger.warning(msg)

        if self.storage_backend == "s3" and not all(
            [self.aws_bucket_name, self.aws_access_key_id, self.aws_secret_access_key]
        ):
            msg = "AWS_BUCKET_NAME, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY are required when STORAGE_BACKEND=s3."
            if self.app_env == "production":
                raise ValueError(msg)
            logger.warning(msg)

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Uses lru_cache so the .env file is read exactly once per process.
    In tests, call get_settings.cache_clear() before patching env vars.
    """
    settings = Settings()
    logger.info(
        "MAE settings loaded — env=%s db=%s llm=%s storage=%s tasks=%s sandbox=%s",
        settings.app_env,
        settings.db_backend,
        settings.llm_provider,
        settings.storage_backend,
        settings.task_backend,
        settings.sandbox_backend,
    )
    return settings
