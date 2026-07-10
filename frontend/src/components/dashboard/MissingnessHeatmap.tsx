/**
 * frontend/src/components/dashboard/MissingnessHeatmap.tsx
 *
 * Visual null-pattern heatmap for the Overview tab.
 *
 * Renders a grid where each cell represents one column's null rate.
 * Colour intensity maps to null density — white = 0%, deep red = 100%.
 * Columns are sorted by null rate descending so the worst offenders
 * appear first.
 *
 * Uses SVG for the grid so no Plotly bundle is needed for this panel.
 * Only columns with at least one null are shown; if everything is clean
 * a "No missing data" message is rendered instead.
 *
 * Usage:
 *   <MissingnessHeatmap hotspots={narrative.missingness_hotspots} />
 */

import React, { useState } from "react";
import type { MissingnessHotspot } from "../../types/chart";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MissingnessHeatmapProps {
  hotspots: MissingnessHotspot[];
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Colour interpolation: white → amber → red
// ---------------------------------------------------------------------------

// Ramp uses the prototype severity tokens so it adapts to both themes:
// overlay (clean) → med-soft → high-soft → high (solid) → crit (solid).
function nullRateColor(rate: number): string {
  const r = Math.min(1, Math.max(0, rate));
  if (r < 0.01) return "var(--sage-bg-overlay)";
  if (r < 0.20) return "var(--sage-med-soft)";
  if (r < 0.40) return "var(--sage-high-soft)";
  if (r < 0.60) return "var(--sage-high)";
  return "var(--sage-crit)";
}

function textColor(rate: number): string {
  // Solid high/crit fills need white text; soft fills follow the theme.
  return rate >= 0.40 ? "#ffffff" : "var(--sage-text-primary)";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MissingnessHeatmap({
  hotspots,
  className = "",
}: MissingnessHeatmapProps): React.ReactElement {
  const [tooltip, setTooltip] = useState<{ col: string; rate: number } | null>(null);

  // Sort worst first, cap at 30 columns for readability
  const sorted = [...hotspots]
    .filter((h) => h.null_rate > 0)
    .sort((a, b) => b.null_rate - a.null_rate)
    .slice(0, 30);

  if (sorted.length === 0) {
    return (
      <div
        className={[
          "flex items-center justify-center rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-8",
          className,
        ].join(" ")}
      >
        <div className="text-center">
          <svg className="mx-auto h-8 w-8 text-[var(--sage-good)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="mt-2 text-sm font-medium text-[var(--sage-good)]">No missing data</p>
          <p className="mt-0.5 text-xs text-[var(--sage-text-dim)]">All columns are complete.</p>
        </div>
      </div>
    );
  }

  const CELL_W = 72;
  const CELL_H = 48;
  const LABEL_H = 24;
  const COLS = Math.min(sorted.length, 6);
  const ROWS = Math.ceil(sorted.length / COLS);
  const SVG_W = COLS * CELL_W;
  const SVG_H = ROWS * (CELL_H + LABEL_H);

  return (
    <div
      className={[
        "rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-5",
        className,
      ].join(" ")}
    >
      <h3 className="mb-3 text-sm font-semibold text-[var(--sage-text-primary)]">
        Missingness Heatmap
      </h3>

      <div className="overflow-x-auto">
        <svg
          width={SVG_W}
          height={SVG_H}
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          role="img"
          aria-label="Column null rate heatmap"
        >
          {sorted.map((h, i) => {
            const col = i % COLS;
            const row = Math.floor(i / COLS);
            const x = col * CELL_W;
            const y = row * (CELL_H + LABEL_H);
            const fill = nullRateColor(h.null_rate);
            const txt = textColor(h.null_rate);
            const pct = `${(h.null_rate * 100).toFixed(0)}%`;

            return (
              <g
                key={h.column}
                onMouseEnter={() => setTooltip({ col: h.column, rate: h.null_rate })}
                onMouseLeave={() => setTooltip(null)}
                style={{ cursor: "default" }}
              >
                {/* Cell */}
                <rect
                  x={x + 2}
                  y={y}
                  width={CELL_W - 4}
                  height={CELL_H}
                  rx={4}
                  fill={fill}
                />
                {/* Percentage label */}
                <text
                  x={x + CELL_W / 2}
                  y={y + CELL_H / 2 + 5}
                  textAnchor="middle"
                  fontSize="13"
                  fontWeight="600"
                  fontFamily="Inter, system-ui, sans-serif"
                  fill={txt}
                >
                  {pct}
                </text>
                {/* Column name */}
                <text
                  x={x + CELL_W / 2}
                  y={y + CELL_H + 16}
                  textAnchor="middle"
                  fontSize="9"
                  fontFamily="Inter, system-ui, sans-serif"
                  fill="var(--sage-text-dim)"
                >
                  {h.column.length > 10 ? `${h.column.slice(0, 9)}…` : h.column}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div className="mt-2 rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-overlay)] px-3 py-1.5 text-xs">
          <span className="font-mono font-medium text-[var(--sage-text-primary)]">{tooltip.col}</span>
          <span className="text-[var(--sage-text-muted)]">
            {" — "}{(tooltip.rate * 100).toFixed(1)}% null
          </span>
        </div>
      )}

      {/* Legend */}
      <div className="mt-3 flex items-center gap-2 text-xs text-[var(--sage-text-dim)]">
        <span>0%</span>
        <div className="flex h-2 flex-1 overflow-hidden rounded-full">
          {[
            "var(--sage-bg-overlay)",
            "var(--sage-med-soft)",
            "var(--sage-high-soft)",
            "var(--sage-high)",
            "var(--sage-crit)",
          ].map((c) => (
            <div key={c} className="flex-1" style={{ backgroundColor: c }} />
          ))}
        </div>
        <span>100%</span>
      </div>
    </div>
  );
}
