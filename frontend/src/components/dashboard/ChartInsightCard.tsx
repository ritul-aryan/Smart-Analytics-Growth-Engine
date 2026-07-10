/**
 * frontend/src/components/dashboard/ChartInsightCard.tsx
 *
 * Programmatic statistical insight text rendered below each chart in
 * the EDA portfolio tab.
 *
 * Displays the chart's insight_text with a subtle icon and optional
 * columns_used pill list.  All content is programmatically computed by
 * the Storyteller agent — no LLM output is displayed here.
 *
 * Usage:
 *   <ChartInsightCard
 *     insight="Strong positive correlation (r=0.82) between age and income."
 *     columnsUsed={["age", "income"]}
 *   />
 */

import React from "react";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChartInsightCardProps {
  /** Programmatic insight string from the Storyteller agent. */
  insight: string;
  /** Column names used in the chart — rendered as grey pills. */
  columnsUsed?: string[];
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Icon
// ---------------------------------------------------------------------------

function InsightIcon(): React.ReactElement {
  return (
    <svg
      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--sage-accent)]"
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 2.5a1 1 0 110 2 1 1 0 010-2zm-.75 3.25a.75.75 0 011.5 0v3.5a.75.75 0 01-1.5 0v-3.5z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChartInsightCard({
  insight,
  columnsUsed = [],
  className = "",
}: ChartInsightCardProps): React.ReactElement | null {
  if (!insight && columnsUsed.length === 0) return null;

  return (
    <div
      className={[
        "rounded-b-xl border-t px-4 py-2.5",
        "border-[var(--sage-border)] bg-[var(--sage-bg-overlay)]",
        className,
      ].join(" ")}
    >
      {insight && (
        <div className="flex items-start gap-1.5">
          <InsightIcon />
          <p className="text-xs leading-relaxed text-[var(--sage-text-muted)]">
            {insight}
          </p>
        </div>
      )}

      {columnsUsed.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {columnsUsed.map((col) => (
            <span
              key={col}
              className={[
                "rounded-full px-2 py-0.5 font-mono text-xs",
                "bg-[var(--sage-bg-elevated)] text-[var(--sage-text-muted)]",
              ].join(" ")}
            >
              {col}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
