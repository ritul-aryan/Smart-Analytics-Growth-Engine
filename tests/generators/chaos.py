"""
tests/generators/chaos.py

Synthetic messy dataset generator for integration and stress testing.

Produces a pandas DataFrame (and optionally a CSV file) that deliberately
contains every class of data quality issue the MAE pipeline is designed to
detect and fix:

  • Missing values (NaN) at configurable densities per column
  • Duplicate rows (exact and near-duplicate)
  • Outliers / statistical anomalies in numeric columns
  • Zero-as-missing substitutions
  • PII-like data (email, phone, SSN patterns) in string columns
  • Mixed-type columns (numbers stored as strings, e.g. "42.0", "$1,200")
  • Inconsistent category spellings  (e.g. "New York", "new york", "NY")
  • Logical violations (age < 0, revenue < cost, end_date < start_date)
  • High null-density rows (rows where > 60 % of values are NaN)
  • Unicode noise and leading/trailing whitespace in string columns

All thresholds are configurable via constructor arguments so individual
test cases can dial the severity up or down.

Usage (CLI):
    python -m tests.generators.chaos --rows 5000 --out ./data/chaos.csv

Usage (Python):
    from tests.generators.chaos import ChaosGenerator
    df = ChaosGenerator(n_rows=1000, seed=42).generate()
"""

from __future__ import annotations

import argparse
import random
import string
from pathlib import Path

import numpy as np
import pandas as pd


class ChaosGenerator:
    """
    Generate a deliberately messy DataFrame for pipeline testing.

    Parameters
    ----------
    n_rows:             Number of rows to generate (before duplicates are injected).
    seed:               Random seed for reproducibility.
    null_rate_low:      Null injection rate for low-density columns  (0–1).
    null_rate_high:     Null injection rate for high-density columns (0–1).
    duplicate_frac:     Fraction of rows to duplicate (0–1).
    outlier_frac:       Fraction of numeric rows to replace with an outlier (0–1).
    zero_as_missing_frac: Fraction of numeric rows to replace with 0 (0–1).
    high_null_row_frac: Fraction of rows to corrupt to > 60 % null density.
    """

    # Column definitions: (name, dtype_tag)
    # dtype_tag in {numeric, category, text, date, pii_email, pii_phone}
    _SCHEMA = [
        ("age",           "numeric"),
        ("income",        "numeric"),
        ("score",         "numeric"),
        ("revenue",       "numeric"),
        ("cost",          "numeric"),
        ("city",          "category"),
        ("country",       "category"),
        ("product",       "category"),
        ("notes",         "text"),
        ("email",         "pii_email"),
        ("phone",         "pii_phone"),
        ("signup_date",   "date"),
        ("last_login",    "date"),
        ("mixed_numeric", "mixed"),
    ]

    _CITIES = [
        "New York", "new york", "NY", "Los Angeles", "LA", "los angeles",
        "Chicago", "chicago", "CHI", "Houston", "houston", "Miami",
    ]
    _COUNTRIES = ["USA", "US", "United States", "Canada", "CA", "UK", "United Kingdom"]
    _PRODUCTS  = ["Widget A", "widget a", "WIDGET A", "Widget B", "Widget C", "Widget c"]

    def __init__(
        self,
        n_rows:               int   = 2000,
        seed:                 int   = 0,
        null_rate_low:        float = 0.05,
        null_rate_high:       float = 0.45,
        duplicate_frac:       float = 0.04,
        outlier_frac:         float = 0.03,
        zero_as_missing_frac: float = 0.03,
        high_null_row_frac:   float = 0.02,
    ) -> None:
        self.n_rows               = n_rows
        self.seed                 = seed
        self.null_rate_low        = null_rate_low
        self.null_rate_high       = null_rate_high
        self.duplicate_frac       = duplicate_frac
        self.outlier_frac         = outlier_frac
        self.zero_as_missing_frac = zero_as_missing_frac
        self.high_null_row_frac   = high_null_row_frac
        self._rng                 = np.random.default_rng(seed)
        random.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> pd.DataFrame:
        """Return a messy DataFrame ready for pipeline ingestion."""
        df = self._base_frame()
        df = self._inject_nulls(df)
        df = self._inject_outliers(df)
        df = self._inject_zero_as_missing(df)
        df = self._inject_logical_violations(df)
        df = self._inject_duplicates(df)
        df = self._inject_high_null_rows(df)
        df = self._inject_whitespace_noise(df)
        df = df.sample(frac=1, random_state=self.seed).reset_index(drop=True)
        return df

    def save(self, path: str | Path) -> Path:
        """Generate and write to a CSV file. Returns the resolved path."""
        out = Path(path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        self.generate().to_csv(out, index=False)
        return out

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _base_frame(self) -> pd.DataFrame:
        n = self.n_rows
        rng = self._rng

        age      = rng.integers(18, 80, size=n).astype(float)
        income   = rng.normal(55_000, 20_000, size=n).clip(10_000, 250_000)
        score    = rng.uniform(0, 100, size=n)
        cost     = rng.uniform(100, 5_000, size=n)
        revenue  = cost + rng.uniform(0, 3_000, size=n)    # revenue > cost (logical)

        city     = rng.choice(self._CITIES,    size=n)
        country  = rng.choice(self._COUNTRIES, size=n)
        product  = rng.choice(self._PRODUCTS,  size=n)

        notes    = np.array([self._random_text() for _ in range(n)])

        emails   = np.array([
            f"user{i}@{''.join(random.choices(string.ascii_lowercase, k=5))}.com"
            for i in range(n)
        ])
        phones   = np.array([
            f"{''.join(random.choices(string.digits, k=3))}-"
            f"{''.join(random.choices(string.digits, k=3))}-"
            f"{''.join(random.choices(string.digits, k=4))}"
            for _ in range(n)
        ])

        start = pd.Timestamp("2020-01-01").value // 10**9
        end   = pd.Timestamp("2024-12-31").value // 10**9
        ts    = rng.integers(start, end, size=n)
        signup_date = pd.to_datetime(ts, unit="s").strftime("%Y-%m-%d")
        last_login  = pd.to_datetime(
            rng.integers(start, end, size=n), unit="s"
        ).strftime("%Y-%m-%d")

        # Mixed-type: mostly numeric strings, some with currency symbols
        mixed = [
            f"${v:,.2f}" if rng.random() < 0.15 else str(round(float(v), 2))
            for v in rng.uniform(10, 10_000, size=n)
        ]

        return pd.DataFrame({
            "age":           age,
            "income":        income,
            "score":         score,
            "revenue":       revenue,
            "cost":          cost,
            "city":          city,
            "country":       country,
            "product":       product,
            "notes":         notes,
            "email":         emails,
            "phone":         phones,
            "signup_date":   signup_date,
            "last_login":    last_login,
            "mixed_numeric": mixed,
        })

    def _inject_nulls(self, df: pd.DataFrame) -> pd.DataFrame:
        rng  = self._rng
        low  = ["age", "score", "product", "last_login"]
        high = ["income", "notes", "phone", "mixed_numeric"]
        for col in low:
            mask = rng.random(len(df)) < self.null_rate_low
            df.loc[mask, col] = np.nan
        for col in high:
            mask = rng.random(len(df)) < self.null_rate_high
            df.loc[mask, col] = np.nan
        return df

    def _inject_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        rng = self._rng
        for col in ["age", "income", "score", "revenue"]:
            idx = rng.choice(len(df), size=max(1, int(len(df) * self.outlier_frac)), replace=False)
            if col == "age":
                df.loc[idx, col] = rng.choice([-5, 150, 999], size=len(idx))
            elif col == "income":
                df.loc[idx, col] = rng.choice([-50_000, 5_000_000], size=len(idx))
            else:
                df.loc[idx, col] = rng.uniform(-1000, 10_000, size=len(idx))
        return df

    def _inject_zero_as_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        rng = self._rng
        for col in ["income", "revenue", "score"]:
            idx = rng.choice(len(df), size=max(1, int(len(df) * self.zero_as_missing_frac)), replace=False)
            df.loc[idx, col] = 0.0
        return df

    def _inject_logical_violations(self, df: pd.DataFrame) -> pd.DataFrame:
        # revenue < cost (logical violation)
        idx = self._rng.choice(
            len(df), size=max(1, int(len(df) * 0.02)), replace=False
        )
        df.loc[idx, "revenue"] = df.loc[idx, "cost"] * self._rng.uniform(0.1, 0.9, size=len(idx))
        # age < 0 already handled by outlier injection
        return df

    def _inject_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        n_dup = max(1, int(len(df) * self.duplicate_frac))
        sample = df.sample(n=n_dup, random_state=self.seed)
        return pd.concat([df, sample], ignore_index=True)

    def _inject_high_null_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        n_bad = max(1, int(len(df) * self.high_null_row_frac))
        idx   = self._rng.choice(len(df), size=n_bad, replace=False)
        cols  = list(df.columns)
        # Null out 70–90 % of columns in each chosen row
        for i in idx:
            n_null = int(len(cols) * self._rng.uniform(0.70, 0.90))
            null_cols = self._rng.choice(cols, size=n_null, replace=False)
            df.loc[i, null_cols] = np.nan
        return df

    def _inject_whitespace_noise(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in ["city", "country", "product", "notes"]:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda v: f"  {v}  " if isinstance(v, str) and self._rng.random() < 0.10 else v
                )
        return df

    @staticmethod
    def _random_text(min_words: int = 3, max_words: int = 12) -> str:
        words = random.choices(
            ["customer", "product", "issue", "resolved", "pending", "great",
             "poor", "delayed", "refund", "support", "feedback", "urgent"],
            k=random.randint(min_words, max_words),
        )
        return " ".join(words)


# =============================================================================
# CLI entry point
# =============================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a synthetic messy CSV for MAE pipeline testing.",
    )
    p.add_argument("--rows",  type=int,   default=2000,              help="Number of base rows (default: 2000)")
    p.add_argument("--seed",  type=int,   default=0,                 help="Random seed (default: 0)")
    p.add_argument("--out",   type=str,   default="./data/chaos.csv", help="Output CSV path")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    gen  = ChaosGenerator(n_rows=args.rows, seed=args.seed)
    path = gen.save(args.out)
    df   = pd.read_csv(path)
    print(f"Saved {len(df):,} rows × {len(df.columns)} columns → {path}")
    print(f"Null rates:\n{df.isnull().mean().round(3).to_string()}")
