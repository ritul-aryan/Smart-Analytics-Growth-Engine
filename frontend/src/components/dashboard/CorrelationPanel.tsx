/**
 * frontend/src/components/dashboard/CorrelationPanel.tsx
 *
 * Top correlations summary panel for the Overview tab.
 *
 * Displays the top-3 Spearman correlations computed deterministically by
 * the Storyteller agent.  Each row shows the two column names, the
 * correlation coefficient, and a horizontal bar indicating strength and
 * direction (positive = accent violet, negative = crit rose).
 *
 * Usage:
 *   <CorrelationPanel correlations={narrative.top_correlations} />
 */

import React from "react";
import type { Correlation } from "../../types/chart";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CorrelationPanelProps {
  correlations: Correlation[];
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Null/NaN-safe formatter — returns "—" for invalid values. */
const fmtR = (r: number | null | undefined): string => {
  if (r == null || isNaN(r)) return "—";
  return (r >= 0 ? "+" : "") + r.toFixed(2);
};

function strengthLabel(r: number): string {
  const abs = Math.abs(r);
  if (abs >= 0.7) return "Strong";
  if (abs >= 0.4) return "Moderate";
  return "Weak";
}

function directionLabel(r: number): string {
  return r >= 0 ? "positive" : "negative";
}

/** Return true only for rows with a finite, non-null correlation. */
function isValidCorrelation(c: Correlation): boolean {
  return c.spearman_r != null && isFinite(c.spearman_r) && !isNaN(c.spearman_r);
}

// ---------------------------------------------------------------------------
// Bar for a single correlation row
// ---------------------------------------------------------------------------

function CorrelationBar({ r }: { r: number }): React.ReactElement {
  const pct = Math.abs(r) * 100;
  const isPositive = r >= 0;

  return (
    <div className="flex items-center gap-2">
      {/* Negative side */}
      <div className="flex w-16 justify-end">
        {!isPositive && (
          <div
            className="h-2 rounded-l-full bg-[var(--sage-crit)]"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>

      {/* Centre line */}
      <div className="h-3 w-px bg-[var(--sage-border-strong)]" />

      {/* Positive side */}
      <div className="w-16">
        {isPositive && (
          <div
            className="h-2 rounded-r-full bg-[var(--sage-accent)]"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CorrelationPanel({
  correlations,
  className = "",
}: CorrelationPanelProps): React.ReactElement {
  const valid = correlations.filter(isValidCorrelation);

  return (
    <div
      className={[
        "rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-5",
        className,
      ].join(" ")}
    >
      <h3 className="mb-4 text-sm font-semibold text-[var(--sage-text-primary)]">
        Top Correlations
      </h3>

      {valid.length === 0 ? (
        <p className="py-4 text-center text-xs text-[var(--sage-text-dim)]">
          No significant correlations found.
        </p>
      ) : (
        <div className="space-y-3">
          {valid.map((c, i) => (
            <div key={i} className="space-y-1">
              {/* Column pair */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1 text-xs">
                  <span className="truncate font-mono font-medium text-[var(--sage-text-primary)]">
                    {c.col_a}
                  </span>
                  <span className="shrink-0 text-[var(--sage-text-dim)]">×</span>
                  <span className="truncate font-mono font-medium text-[var(--sage-text-primary)]">
                    {c.col_b}
                  </span>
                </div>
                <div className="shrink-0 text-right">
                  <span
                    className={[
                      "text-xs font-semibold tabular-nums",
                      c.spearman_r >= 0
                        ? "text-[var(--sage-accent)]"
                        : "text-[var(--sage-crit)]",
                    ].join(" ")}
                  >
                    {fmtR(c.spearman_r)}
                  </span>
                </div>
              </div>

              {/* Bar */}
              <CorrelationBar r={c.spearman_r} />

              {/* Strength label */}
              <p className="text-xs text-[var(--sage-text-dim)]">
                {strengthLabel(c.spearman_r)} {directionLabel(c.spearman_r)} correlation
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="mt-4 flex items-center justify-center gap-4 border-t border-[var(--sage-border)] pt-3 text-xs text-[var(--sage-text-dim)]">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-4 rounded-full bg-[var(--sage-crit)]" />
          Negative
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-4 rounded-full bg-[var(--sage-accent)]" />
          Positive
        </span>
      </div>
    </div>
  );
}
