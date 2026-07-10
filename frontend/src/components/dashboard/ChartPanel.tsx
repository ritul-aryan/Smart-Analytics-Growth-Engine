/**
 * frontend/src/components/dashboard/ChartPanel.tsx
 *
 * Renders a single Plotly chart from a ChartSpec.
 * Uses direct Plotly.js API (useRef + useEffect) -- not react-plotly.js.
 */

import { useEffect, useRef } from "react";
import type { ChartSpec } from "../../types/chart";

// @types/plotly.js uses UMD namespace exports - not default-importable.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyPlotly = any;

interface ChartPanelProps {
  chart: ChartSpec;
}

// Lazy-import Plotly to keep the initial bundle small
async function getPlotly(): Promise<AnyPlotly> {
  const mod = await import("plotly.js");
  return (mod.default ?? mod) as AnyPlotly;
}

export default function ChartPanel({ chart }: ChartPanelProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    let cancelled = false;

    getPlotly().then((Plotly) => {
      if (cancelled || !el) return;
      const config: Record<string, unknown> = {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["sendDataToCloud"],
      };
      const layout: Record<string, unknown> = {
        autosize: true,
        margin: { l: 48, r: 24, t: 40, b: 48 },
        font: { family: "Inter, system-ui, sans-serif", size: 12 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        ...chart.plotly_config.layout,
      };
      void Plotly.newPlot(el, chart.plotly_config.data, layout, config);
    }).catch(console.error);

    return () => {
      cancelled = true;
      getPlotly().then((Plotly) => Plotly.purge(el)).catch(() => undefined);
    };
  }, [chart]);

  return (
    <div className="overflow-hidden rounded-xl bg-[var(--sage-bg-elevated)] shadow-sm ring-1 ring-[var(--sage-border)]">
      <div className="px-5 pt-4 pb-1">
        <h3 className="truncate text-sm font-semibold text-[var(--sage-text-primary)]">{chart.title}</h3>
        {chart.columns_used.length > 0 && (
          <p className="mt-0.5 text-xs text-[var(--sage-text-dim)]">
            {chart.columns_used.join(" \xb7 ")}
          </p>
        )}
      </div>
      <div ref={containerRef} className="h-72 w-full" aria-label={chart.title} />
      {chart.insight_text && (
        <p className="border-t border-[var(--sage-border)] px-5 py-3 text-xs text-[var(--sage-text-muted)]">
          {chart.insight_text}
        </p>
      )}
    </div>
  );
}
