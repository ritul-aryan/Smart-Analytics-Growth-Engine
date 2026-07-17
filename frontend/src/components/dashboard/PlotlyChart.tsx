/**
 * frontend/src/components/dashboard/PlotlyChart.tsx
 *
 * Plotly chart wrapper — SAGE dark theme applied to every chart.
 *
 * Plotly is loaded via CDN <script> in index.html (not bundled).
 * window.Plotly is available synchronously before React hydrates.
 *
 * INTENTIONAL EXCEPTION to the --sage-* token rule: chart cards keep a
 * FIXED dark canvas in both themes (see index.css design note — analytics
 * tools pair a light chrome with dark data-viz canvases). Plotly cannot
 * resolve CSS var() strings, so the dark-palette values from the SAGE.html
 * prototype are pinned here as the CANVAS_* constants below. Accent colours
 * are identical in both themes, so those still use var(--sage-accent*).
 *
 * Canvas constants (prototype dark palette):
 *   paper/plot background   #161A23   (--card)
 *   font colour             #ECEEF2   (--text)
 *   axis grid / line        rgba(255,255,255,0.12)  (--border2)
 *   axis label colour       #9097A3   (--text2)
 *   margin                  { t:30, r:20, b:40, l:50 }
 *
 * Render strategy:
 *   First render  → Plotly.newPlot  (creates SVG into the div)
 *   Re-render     → Plotly.react    (in-place diff, no flicker)
 *   Unmount       → Plotly.purge    (releases memory)
 *   Resize        → Plotly.Plots.resize via ResizeObserver
 */

import React, { useEffect, useRef, useCallback } from "react";
import type { ChartSpec } from "../../types/chart";

// ---------------------------------------------------------------------------
// SAGE dark theme — merged into every chart layout before render
// ---------------------------------------------------------------------------

// Fixed dark-canvas palette (prototype values) — see header comment.
// Card/insight borders use the literal rgba(255,255,255,0.07) inside
// Tailwind arbitrary-value classes below (the JIT scanner requires static
// class strings, so that value cannot be referenced via a constant).
const CANVAS_BG     = "#161A23";
const CANVAS_TEXT   = "#ECEEF2";
const CANVAS_MUTED  = "#9097A3";
const CANVAS_GRID   = "rgba(255,255,255,0.12)";

const DARK_LAYOUT = {
  paper_bgcolor: CANVAS_BG,
  plot_bgcolor:  CANVAS_BG,
  font: {
    color:  CANVAS_TEXT,
    family: "Inter, system-ui, sans-serif",
    size:   12,
  },
  xaxis: {
    gridcolor:     CANVAS_GRID,
    linecolor:     CANVAS_GRID,
    color:         CANVAS_MUTED,
    zerolinecolor: CANVAS_GRID,
  },
  yaxis: {
    gridcolor:     CANVAS_GRID,
    linecolor:     CANVAS_GRID,
    color:         CANVAS_MUTED,
    zerolinecolor: CANVAS_GRID,
  },
  margin: { t: 30, r: 20, b: 40, l: 50 },
  autosize: true,
} as const;

// ---------------------------------------------------------------------------
// window.Plotly accessor (CDN global)
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getPlotly(): any {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const p = (window as any).Plotly;
  if (!p) {
    console.error("[PlotlyChart] window.Plotly undefined — CDN script missing from index.html");
  }
  return p ?? null;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PlotlyChartProps {
  chart: ChartSpec;
  /** Container height in px. Default: 300. */
  height?: number;
  /** Show PNG/SVG export buttons. Default: true. */
  showExport?: boolean;
  /** Extra Tailwind classes for the outer card. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Export helpers
// ---------------------------------------------------------------------------

function exportChart(el: HTMLDivElement, format: "png" | "svg"): void {
  const Plotly = getPlotly();
  if (!Plotly) return;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (Plotly.toImage(el, { format, width: 1200, height: 600 }) as Promise<any>)
    .then((url: string) => {
      const a = document.createElement("a");
      a.href = url;
      a.download = "chart." + format;
      a.click();
    })
    .catch(console.error);
}

function ExportBtn({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded px-2 py-0.5 text-xs font-medium border border-[rgba(255,255,255,0.12)] text-[#9097A3] hover:border-[var(--sage-accent-border)] hover:text-[#ECEEF2] transition-colors"
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function PlotlyChart({
  chart,
  height = 300,
  showExport = true,
  className = "",
}: PlotlyChartProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const hasPlot = useRef(false);

  const renderChart = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const Plotly = getPlotly();
    if (!Plotly) return;

    // Deep-merge: DARK_LAYOUT first, chart's own layout on top.
    // Then re-enforce backgrounds so a chart can never override them.
    // Chart-type-specific post-overrides are applied LAST so they always win.
    const isHeatmap = chart.chart_type === "heatmap";

    const layout = {
      ...DARK_LAYOUT,
      xaxis: { ...DARK_LAYOUT.xaxis },
      yaxis: { ...DARK_LAYOUT.yaxis },
      font:  { ...DARK_LAYOUT.font  },
      ...chart.plotly_config.layout,
      paper_bgcolor: CANVAS_BG,
      plot_bgcolor:  CANVAS_BG,
      // Heatmap overrides: rotate x-axis labels and compute margins dynamically
      // so longer OHE column names (e.g. "product_category_Electronics") never
      // overlap.  _max_label_len is injected by the storyteller into the layout.
      ...(isHeatmap && (() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const maxLen: number = (chart.plotly_config.layout as any)._max_label_len ?? 10;
        // 6 px per character approximation; clamp to sensible min/max
        const labelPx = Math.min(Math.max(maxLen * 6, 80), 260);
        return {
          xaxis:  { ...DARK_LAYOUT.xaxis, tickangle: -45, automargin: true },
          yaxis:  { ...DARK_LAYOUT.yaxis, automargin: true },
          margin: { t: 40, r: 20, b: labelPx, l: labelPx },
        };
      })()),
    };

    const config = {
      responsive: true,
      displaylogo: false,
      displayModeBar: true,
      scrollZoom: true,
      modeBarButtonsToRemove: ["sendDataToCloud"],
    };

    try {
      if (hasPlot.current) {
        Plotly.react(el, chart.plotly_config.data, layout, config);
      } else {
        Plotly.newPlot(el, chart.plotly_config.data, layout, config);
        hasPlot.current = true;
      }
    } catch (err) {
      console.error("[PlotlyChart] render error:", err, chart.title);
    }
  }, [chart]);

  useEffect(() => { renderChart(); }, [renderChart]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver(() => {
      const Plotly = getPlotly();
      if (Plotly && hasPlot.current) {
        try { Plotly.Plots.resize(el); } catch { /* ignore */ }
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    return () => {
      if (el && hasPlot.current) {
        const Plotly = getPlotly();
        if (Plotly) { try { Plotly.purge(el); } catch { /* ignore */ } }
      }
    };
  }, []);

  return (
    <div
      className={[
        "rounded-xl border border-[rgba(255,255,255,0.07)] bg-[#161A23]",
        className,
      ].join(" ")}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 px-4 pt-3 pb-1">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-[#ECEEF2]">
            {chart.title}
          </h3>
          {chart.columns_used.length > 0 && (
            <p className="mt-0.5 truncate text-xs text-[#9097A3]">
              {chart.columns_used.join(" · ")}
            </p>
          )}
        </div>
        {showExport && (
          <div className="flex shrink-0 items-center gap-1 pt-0.5">
            <ExportBtn
              label="PNG"
              onClick={() => containerRef.current && exportChart(containerRef.current, "png")}
            />
            <ExportBtn
              label="SVG"
              onClick={() => containerRef.current && exportChart(containerRef.current, "svg")}
            />
          </div>
        )}
      </div>

      {/* Chart div -- Plotly writes SVG directly into this element */}
      <div
        ref={containerRef}
        style={{ height, backgroundColor: CANVAS_BG }}
        className="w-full"
        aria-label={chart.title}
        role="img"
      />

      {/* Optional insight text.
          The storyteller now returns a multi-section analysis: sections are
          separated by a blank line ("\n\n") and each begins with an uppercase
          "LABEL —" prefix (e.g. "WHAT THIS SHOWS —", "SHAPE —"). Render each
          section as its own paragraph with the label styled as a small heading.
          Falls back gracefully to a single paragraph for legacy single-line
          insights that contain no blank-line separators. Display-only; the rich
          full-page treatment is a redesign item. */}
      {chart.insight_text && (
        <div className="border-t border-[rgba(255,255,255,0.07)] bg-[var(--sage-accent-soft)] px-4 py-3">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 shrink-0 rounded bg-[var(--sage-accent-soft)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--sage-accent)]">
              Insight
            </span>
            <div className="flex min-w-0 flex-col gap-2">
              {chart.insight_text.split("\n\n").map((section, i) => {
                const dashIdx = section.indexOf(" — ");
                const hasLabel =
                  dashIdx > 0 && section.slice(0, dashIdx) === section.slice(0, dashIdx).toUpperCase();
                if (hasLabel) {
                  const label = section.slice(0, dashIdx);
                  const body = section.slice(dashIdx + 3);
                  return (
                    <p key={i} className="text-xs leading-relaxed text-[#9097A3]">
                      <span className="font-semibold text-[#ECEEF2]">{label}</span>
                      {" — "}
                      {body}
                    </p>
                  );
                }
                return (
                  <p key={i} className="text-xs leading-relaxed text-[#9097A3]">
                    {section}
                  </p>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
