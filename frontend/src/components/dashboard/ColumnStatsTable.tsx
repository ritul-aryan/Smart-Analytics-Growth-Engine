/**
 * frontend/src/components/dashboard/ColumnStatsTable.tsx
 *
 * Per-column statistics table for the Overview tab.
 *
 * Displays: column name, dtype, null count, null rate, unique count,
 * mean, std, min, max, skewness, kurtosis.
 *
 * Data comes from the EDA narrative's numeric_cols / categorical_cols
 * and the session metadata_summary.  When full column-level stats are
 * not available (Phase 3 not yet complete), renders a skeleton.
 *
 * Usage:
 *   <ColumnStatsTable columns={colStats} />
 */

import React, { useState } from "react";
import type { ColumnStat } from "../../types/chart";

// Re-export so existing imports of ColumnStat from this module continue to work.
export type { ColumnStat };

interface ColumnStatsTableProps {
  columns: ColumnStat[];
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(value: number | null, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  if (!isFinite(value)) return "—";
  return value.toFixed(decimals);
}

function fmtPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function NullRateBar({ rate }: { rate: number }): React.ReactElement {
  const pct = Math.min(100, Math.max(0, rate * 100));
  const color =
    pct > 40 ? "bg-[var(--sage-crit)]"
    : pct > 15 ? "bg-[var(--sage-high)]"
    : "bg-[var(--sage-good)]";

  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--sage-bg-overlay)]">
        <div className={["h-full rounded-full", color].join(" ")} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-[var(--sage-text-muted)]">
        {fmtPct(rate)}
      </span>
    </div>
  );
}

type SortKey = keyof ColumnStat;
type SortDir = "asc" | "desc";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ColumnStatsTable({
  columns,
  className = "",
}: ColumnStatsTableProps): React.ReactElement {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function handleSort(key: SortKey): void {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const sorted = [...columns].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  const headers: { key: SortKey; label: string; numeric?: boolean }[] = [
    { key: "name",         label: "Column" },
    { key: "dtype",        label: "Type" },
    { key: "null_count",   label: "Nulls",   numeric: true },
    { key: "null_rate",    label: "Null %",  numeric: true },
    { key: "unique_count", label: "Unique",  numeric: true },
    { key: "mean",         label: "Mean",    numeric: true },
    { key: "std",          label: "Std",     numeric: true },
    { key: "min",          label: "Min",     numeric: true },
    { key: "max",          label: "Max",     numeric: true },
    { key: "skewness",     label: "Skew",    numeric: true },
    { key: "kurtosis",     label: "Kurt",    numeric: true },
  ];

  function SortIcon({ col }: { col: SortKey }): React.ReactElement {
    if (col !== sortKey) {
      return <span className="ml-1 text-[var(--sage-text-dim)]">↕</span>;
    }
    return <span className="ml-1 text-[var(--sage-accent)]">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  return (
    <div
      className={[
        "overflow-x-auto rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]",
        className,
      ].join(" ")}
    >
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--sage-border)]">
            {headers.map((h) => (
              <th
                key={h.key}
                className={[
                  "cursor-pointer select-none whitespace-nowrap px-4 py-2.5 text-xs font-semibold uppercase tracking-wide",
                  "text-[var(--sage-text-muted)] hover:text-[var(--sage-text-primary)]",
                  h.numeric ? "text-right" : "text-left",
                ].join(" ")}
                onClick={() => handleSort(h.key)}
              >
                {h.label}
                <SortIcon col={h.key} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--sage-border)]">
          {sorted.map((col) => (
            <tr
              key={col.name}
              className="transition-colors hover:bg-[var(--sage-bg-overlay)]"
            >
              <td className="px-4 py-2 font-mono text-xs text-[var(--sage-text-primary)]">
                {col.name}
              </td>
              <td className="px-4 py-2">
                <span className="rounded bg-[var(--sage-bg-overlay)] px-1.5 py-0.5 font-mono text-xs text-[var(--sage-text-muted)]">
                  {col.dtype}
                </span>
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">
                {col.null_count.toLocaleString()}
              </td>
              <td className="px-4 py-2">
                <NullRateBar rate={col.null_rate} />
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">
                {col.unique_count.toLocaleString()}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">{fmt(col.mean)}</td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">{fmt(col.std)}</td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">{fmt(col.min)}</td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">{fmt(col.max)}</td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">{fmt(col.skewness)}</td>
              <td className="px-4 py-2 text-right tabular-nums text-xs text-[var(--sage-text-muted)]">{fmt(col.kurtosis)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {columns.length === 0 && (
        <p className="py-8 text-center text-sm text-[var(--sage-text-dim)]">
          Column statistics not yet available.
        </p>
      )}
    </div>
  );
}
