"""
tests/generators/titan.py

Large-scale dataset generator for MAE performance and scalability testing.

Produces a wide, numerically-heavy DataFrame at 50 000–500 000 rows that
exercises:

  • pandas chunked I/O performance
  • Profiler agent runtime at scale
  • Memory usage of the RestrictedExecutor / DockerExecutor sandbox
  • Quality score computation on large column counts

The schema is modelled on a realistic e-commerce transaction log:
  — order_id, customer_id, product_id  (identifiers)
  — timestamps (order_date, ship_date, deliver_date)
  — amounts (unit_price, quantity, discount, total, tax, net_revenue)
  — geography (region, country, city)
  — metrics (customer_ltv, page_views, session_duration, rating)
  — 10 synthetic numeric feature columns (feature_00 … feature_09)

A small configurable fraction of rows / values is corrupted so that the
pipeline has something non-trivial to detect.

Usage (CLI):
    python -m tests.generators.titan --rows 50000 --out ./data/titan.csv

Usage (Python):
    from tests.generators.titan import TitanGenerator
    df = TitanGenerator(n_rows=50_000, seed=42).generate()
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


class TitanGenerator:
    """
    Generate a large realistic e-commerce transaction dataset.

    Parameters
    ----------
    n_rows:         Number of rows.
    seed:           Random seed for reproducibility.
    null_rate:      Fraction of values to nullify in selected columns (0–1).
    outlier_rate:   Fraction of numeric values to replace with extreme values.
    duplicate_frac: Fraction of rows to duplicate.
    n_features:     Number of extra synthetic numeric feature columns (default 10).
    """

    _REGIONS   = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
    _COUNTRIES = ["USA", "Germany", "Japan", "Brazil", "UAE", "UK", "France", "India", "Canada", "Australia"]
    _CITIES    = ["New York", "Berlin", "Tokyo", "São Paulo", "Dubai", "London",
                  "Paris", "Mumbai", "Toronto", "Sydney", "Chicago", "Munich"]
    _CATEGORIES = ["Electronics", "Clothing", "Home & Garden", "Sports", "Books",
                   "Toys", "Automotive", "Beauty", "Food", "Office"]

    def __init__(
        self,
        n_rows:         int   = 50_000,
        seed:           int   = 0,
        null_rate:      float = 0.03,
        outlier_rate:   float = 0.005,
        duplicate_frac: float = 0.01,
        n_features:     int   = 10,
    ) -> None:
        self.n_rows         = n_rows
        self.seed           = seed
        self.null_rate      = null_rate
        self.outlier_rate   = outlier_rate
        self.duplicate_frac = duplicate_frac
        self.n_features     = n_features
        self._rng           = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> pd.DataFrame:
        """Return the full DataFrame."""
        df = self._base_frame()
        df = self._inject_nulls(df)
        df = self._inject_outliers(df)
        df = self._inject_duplicates(df)
        df = df.sample(frac=1, random_state=self.seed).reset_index(drop=True)
        return df

    def save(self, path: str | Path, chunksize: int = 10_000) -> Path:
        """
        Generate and write to CSV in chunks to avoid memory spikes on very
        large datasets.  Returns the resolved output path.
        """
        out = Path(path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        df = self.generate()
        total = len(df)

        # Write header + first chunk, then append remaining chunks
        for i, start in enumerate(range(0, total, chunksize)):
            chunk = df.iloc[start:start + chunksize]
            chunk.to_csv(out, mode="w" if i == 0 else "a", index=False, header=(i == 0))

        return out

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _base_frame(self) -> pd.DataFrame:
        n   = self.n_rows
        rng = self._rng

        # Identifiers
        order_ids    = [f"ORD-{i:08d}" for i in range(n)]
        customer_ids = [f"CUST-{rng.integers(1, n // 5):07d}" for _ in range(n)]
        product_ids  = [f"PROD-{rng.integers(1, 500):05d}"    for _ in range(n)]

        # Dates
        epoch_start = pd.Timestamp("2020-01-01").value // 10**9
        epoch_end   = pd.Timestamp("2024-12-31").value // 10**9
        order_ts    = rng.integers(epoch_start, epoch_end, size=n)
        ship_offset = rng.integers(1, 7,  size=n) * 86400
        deliv_offset= rng.integers(3, 14, size=n) * 86400

        order_date  = pd.to_datetime(order_ts, unit="s").strftime("%Y-%m-%d")
        ship_date   = pd.to_datetime(order_ts + ship_offset,  unit="s").strftime("%Y-%m-%d")
        deliv_date  = pd.to_datetime(order_ts + ship_offset + deliv_offset, unit="s").strftime("%Y-%m-%d")

        # Amounts
        unit_price  = rng.uniform(5, 500, size=n).round(2)
        quantity    = rng.integers(1, 20, size=n).astype(float)
        discount    = rng.uniform(0, 0.4, size=n).round(4)
        subtotal    = (unit_price * quantity * (1 - discount)).round(2)
        tax         = (subtotal * 0.08).round(2)
        net_revenue = (subtotal + tax).round(2)
        cost_base   = (unit_price * quantity * rng.uniform(0.4, 0.7, size=n)).round(2)
        gross_profit= (net_revenue - cost_base).round(2)

        # Geography
        region  = rng.choice(self._REGIONS,    size=n)
        country = rng.choice(self._COUNTRIES,  size=n)
        city    = rng.choice(self._CITIES,     size=n)

        # Product metadata
        category = rng.choice(self._CATEGORIES, size=n)
        rating   = rng.uniform(1, 5, size=n).round(1)

        # Customer behaviour
        customer_ltv     = rng.exponential(500, size=n).round(2)
        page_views       = rng.integers(1, 50, size=n).astype(float)
        session_duration = rng.exponential(180, size=n).round(1)    # seconds
        is_returning     = rng.integers(0, 2, size=n).astype(float)

        data: dict[str, object] = {
            "order_id":        order_ids,
            "customer_id":     customer_ids,
            "product_id":      product_ids,
            "order_date":      order_date,
            "ship_date":       ship_date,
            "deliver_date":    deliv_date,
            "unit_price":      unit_price,
            "quantity":        quantity,
            "discount":        discount,
            "subtotal":        subtotal,
            "tax":             tax,
            "net_revenue":     net_revenue,
            "cost_base":       cost_base,
            "gross_profit":    gross_profit,
            "region":          region,
            "country":         country,
            "city":            city,
            "category":        category,
            "rating":          rating,
            "customer_ltv":    customer_ltv,
            "page_views":      page_views,
            "session_duration":session_duration,
            "is_returning":    is_returning,
        }

        # Synthetic feature columns (useful for PCA / clustering tests)
        for i in range(self.n_features):
            mu  = rng.uniform(-2, 2)
            std = rng.uniform(0.5, 3)
            data[f"feature_{i:02d}"] = rng.normal(mu, std, size=n).round(4)

        return pd.DataFrame(data)

    def _inject_nulls(self, df: pd.DataFrame) -> pd.DataFrame:
        rng          = self._rng
        nullable_cols = ["discount", "rating", "city", "customer_ltv",
                         "page_views", "session_duration"]
        for col in nullable_cols:
            if col in df.columns:
                mask = rng.random(len(df)) < self.null_rate
                df.loc[mask, col] = np.nan
        return df

    def _inject_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        rng     = self._rng
        numeric = ["unit_price", "net_revenue", "gross_profit", "customer_ltv"]
        for col in numeric:
            n_out = max(1, int(len(df) * self.outlier_rate))
            idx   = rng.choice(len(df), size=n_out, replace=False)
            factor = rng.choice([-1, 100], size=n_out)
            df.loc[idx, col] = df.loc[idx, col] * factor
        return df

    def _inject_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        n_dup  = max(1, int(len(df) * self.duplicate_frac))
        sample = df.sample(n=n_dup, random_state=self.seed)
        return pd.concat([df, sample], ignore_index=True)


# =============================================================================
# CLI entry point
# =============================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a large-scale synthetic e-commerce CSV for MAE scalability testing.",
    )
    p.add_argument("--rows",     type=int, default=50_000,           help="Number of base rows (default: 50000)")
    p.add_argument("--seed",     type=int, default=0,                help="Random seed (default: 0)")
    p.add_argument("--features", type=int, default=10,               help="Number of extra numeric feature columns (default: 10)")
    p.add_argument("--out",      type=str, default="./data/titan.csv", help="Output CSV path")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    gen  = TitanGenerator(n_rows=args.rows, seed=args.seed, n_features=args.features)
    path = gen.save(args.out)
    df   = pd.read_csv(path, nrows=5)
    total = sum(1 for _ in open(path)) - 1  # count rows without loading all into memory
    print(f"Saved {total:,} rows × {len(df.columns)} columns → {path}")
