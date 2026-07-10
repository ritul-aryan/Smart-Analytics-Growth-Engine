"""
tests/conftest.py

Shared pytest fixtures for the MAE test suite.

Fixtures provided:
  sample_df     — clean 100-row DataFrame for Phase 1 / Phase 2.5 tests
  dirty_df      — DataFrame with known anomalies (duplicates, nulls, outliers)
  mock_llm      — LLMProvider stub that returns predictable JSON
  db            — per-test async SQLite in-memory session (tables auto-created)
  session_id    — stable UUID string for test sessions
  auditor       — Auditor wired to the test db + session_id
  async_client  — httpx.AsyncClient against the FastAPI app with DB overridden
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_engine.agents.auditor import Auditor
from ai_engine.llm.base import LLMProvider
from backend.db.models import Base
from backend.db.session import get_db
from backend.main import app

# ---------------------------------------------------------------------------
# DataFrames
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Clean 100-row DataFrame — no anomalies, used for engineer + storyteller."""
    rng = np.random.default_rng(42)
    n = 100
    return pd.DataFrame({
        "id":           range(1, n + 1),
        "age":          rng.integers(18, 70, size=n).astype(float),
        "income":       rng.normal(50_000, 15_000, size=n),
        "score":        rng.uniform(0, 100, size=n),
        "city":         rng.choice(["London", "Paris", "Berlin", "Madrid"], size=n),
        "category":     rng.choice(["A", "B", "C"], size=n),
        "signup_date":  pd.date_range("2023-01-01", periods=n, freq="3D"),
    })


@pytest.fixture
def dirty_df() -> pd.DataFrame:
    """100-row DataFrame with known anomalies for orchestrator + janitor tests."""
    rng = np.random.default_rng(7)
    n = 100
    df = pd.DataFrame({
        "id":       range(1, n + 1),
        "age":      rng.integers(18, 70, size=n).astype(float),
        "income":   rng.normal(50_000, 12_000, size=n),
        "city":     rng.choice(["London", "Paris", "Berlin"], size=n),
        "email":    [f"user{i}@example.com" for i in range(n)],
    })
    # T1 — Duplicate rows (rows 0–1 are identical)
    df.iloc[1] = df.iloc[0]
    # T2 — Missing data: 45% nulls in 'income' (triggers danger threshold)
    null_idx = rng.choice(n, size=45, replace=False)
    df.loc[null_idx, "income"] = np.nan
    # T3 — Zero-as-missing: 10 zeros in 'age'
    zero_idx = rng.choice(n, size=10, replace=False)
    df.loc[zero_idx, "age"] = 0.0
    # T4 — Logical violation: 3 negative ages
    df.loc[[5, 6, 7], "age"] = -1.0
    # T5 — Outlier: extreme income value
    df.loc[8, "income"] = 999_999.0
    # Supp — High null density rows: make 5 rows almost entirely null
    for r in [90, 91, 92, 93, 94]:
        df.loc[r, ["age", "income", "city"]] = [np.nan, np.nan, None]
    return df


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class _MockLLM(LLMProvider):
    """Deterministic stub — always returns a valid scatter chart selection."""

    @property
    def name(self) -> str:
        return "mock"

    async def complete(self, prompt: str, *, task: str = "general") -> str:
        return (
            '{"chart_type":"scatter","x_column":"age","y_column":"income",'
            '"color_column":null,"title":"Age vs Income"}'
        )

    async def complete_json(
        self, prompt: str, schema: type = None, *, system: str | None = None, task: str = "general"
    ) -> Any:
        data: dict[str, Any] = {
            "chart_type": "scatter",
            "x_column": "age",
            "y_column": "income",
            "color_column": None,
            "title": "Age vs Income",
        }
        if schema is not None:
            try:
                return schema.model_validate(data)
            except Exception:
                return schema.model_validate({})
        return data


@pytest.fixture
def mock_llm() -> LLMProvider:
    return _MockLLM()


# ---------------------------------------------------------------------------
# Test DB (in-memory SQLite, tables created fresh per test)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def auditor(db: AsyncSession, session_id: str) -> Auditor:
    return Auditor(db=db, session_id=session_id)


# ---------------------------------------------------------------------------
# FastAPI async test client (DB dependency overridden)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
