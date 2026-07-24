/**
 * frontend/src/components/dashboard/CustomVizPanel.tsx
 *
 * Natural language chart builder for the Custom Visualisation tab.
 */

import React, { Component, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { sendChatMessage } from "../../api/chat";
import PlotlyChart from "./PlotlyChart";
import type { ChartSpec } from "../../types/chart";

interface EBState { hasError: boolean }

class ChartErrorBoundary extends Component<
  { children: React.ReactNode },
  EBState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(_err: unknown): EBState {
    return { hasError: true };
  }

  override render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-[var(--sage-crit)] bg-[var(--sage-crit-soft)] p-8 text-center">
          <svg className="h-8 w-8 text-[var(--sage-crit)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
          </svg>
          <p className="text-sm font-medium text-[var(--sage-crit)]">This chart cannot be rendered with the selected data.</p>
          <p className="max-w-xs text-xs text-[var(--sage-text-muted)]">Try a different chart type or column combination.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

interface CustomVizPanelProps {
  sessionId: string;
  savedCharts?: ChartSpec[];
  className?: string;
}

const EXAMPLES = [
  "Show me the distribution of income as a histogram",
  "Scatter plot of age vs income",
  "Bar chart of count by city",
  "Box plot of score by category",
];

export default function CustomVizPanel({
  sessionId,
  savedCharts = [],
  className = "",
}: CustomVizPanelProps): React.ReactElement {
  const [prompt, setPrompt] = useState("");
  const [localCharts, setLocalCharts] = useState<ChartSpec[]>(savedCharts);
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [lastError, setLastError] = useState<string | null>(null);

  const { mutate: generate, isPending } = useMutation({
    mutationFn: (message: string) => sendChatMessage(sessionId, message),
    onSuccess: (data) => {
      setLastError(null);
      if (data.chart) {
        setLocalCharts((prev) => [data.chart as ChartSpec, ...prev]);
      } else {
        setLastError(
          "The LLM returned a text answer instead of a chart. " +
          "Try rephrasing with a chart type keyword (e.g. 'histogram', 'scatter', 'bar').",
        );
      }
    },
    onError: () => {
      setLastError("Failed to reach the server. Please try again.");
    },
  });

  function handleSubmit(e: React.FormEvent): void {
    e.preventDefault();
    const text = prompt.trim();
    if (!text || isPending) return;
    setPrompt("");
    generate(text);
  }

  function handleExample(ex: string): void {
    setPrompt(ex);
  }

  function handleDelete(id: string): void {
    setDeletedIds((prev) => new Set([...prev, id]));
  }

  const visibleCharts = localCharts.filter((c) => !deletedIds.has(c.id));

  return (
    <div className={["mx-auto w-full max-w-5xl space-y-6", className].join(" ")}>
      <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent-soft)]">
            <svg className="h-4 w-4 text-[var(--sage-accent)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M10 2a.75.75 0 01.692.462l1.41 3.393 3.664.293a.75.75 0 01.428 1.317l-2.79 2.39.85 3.575a.75.75 0 01-1.12.813L10 12.347l-3.134 1.896a.75.75 0 01-1.12-.813l.85-3.575-2.79-2.39a.75.75 0 01.428-1.317l3.665-.293 1.41-3.393A.75.75 0 0110 2z" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">Custom Visualisation</h3>
            <p className="text-xs text-[var(--sage-text-muted)]">Describe a chart in plain English and the AI will generate it.</p>
          </div>
        </div>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => handleExample(ex)}
              className={[
                "rounded-full border px-3 py-1.5 text-xs transition-colors",
                "border-[var(--sage-border-strong)] text-[var(--sage-text-muted)]",
                "hover:border-[var(--sage-accent-border)] hover:bg-[var(--sage-accent-soft)] hover:text-[var(--sage-accent)]",
              ].join(" ")}
            >
              {ex}
            </button>
          ))}
        </div>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. Show sales by region as a bar chart…"
            disabled={isPending}
            className={[
              "flex-1 rounded-xl border px-3.5 py-2 text-sm outline-none transition-colors",
              "border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] text-[var(--sage-text-primary)]",
              "placeholder:text-[var(--sage-text-dim)]",
              "focus:border-[var(--sage-accent-border)] focus:ring-2 focus:ring-[var(--sage-accent-soft)]",
              isPending ? "opacity-60" : "",
            ].join(" ")}
          />
          <button
            type="submit"
            disabled={isPending || !prompt.trim()}
            className={[
              "rounded-xl px-4 py-2 text-sm font-medium transition-colors",
              "bg-[var(--sage-accent)] text-white hover:opacity-90",
              "disabled:cursor-not-allowed disabled:opacity-40",
            ].join(" ")}
          >
            {isPending ? "Generating…" : "Generate"}
          </button>
        </form>
        {lastError && (
          <p className="mt-2 text-xs text-[var(--sage-crit)]">{lastError}</p>
        )}
        {isPending && (
          <div className="mt-3 flex items-center gap-2 text-xs text-[var(--sage-text-dim)]">
            <div className="h-3 w-3 animate-spin rounded-full border border-[var(--sage-border-strong)] border-t-[var(--sage-accent)]" />
            Asking the AI…
          </div>
        )}
      </div>
      {visibleCharts.length > 0 && (
        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--sage-text-dim)]">
            Generated charts ({visibleCharts.length})
          </p>
          {visibleCharts.map((chart) => (
            <div key={chart.id} className="relative rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-4">
              <ChartErrorBoundary>
                <PlotlyChart chart={chart} height={280} />
              </ChartErrorBoundary>
              <button
                type="button"
                onClick={() => handleDelete(chart.id)}
                aria-label="Remove chart"
                className={[
                  "absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full",
                  "bg-[var(--sage-bg-overlay)] text-[var(--sage-text-muted)] shadow-sm",
                  "hover:bg-[var(--sage-crit-soft)] hover:text-[var(--sage-crit)]",
                ].join(" ")}
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">
                  <path d="M3.22 3.22a.75.75 0 011.06 0L7 5.94l2.72-2.72a.75.75 0 111.06 1.06L8.06 7l2.72 2.72a.75.75 0 11-1.06 1.06L7 8.06l-2.72 2.72a.75.75 0 01-1.06-1.06L5.94 7 3.22 4.28a.75.75 0 010-1.06z" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
      {visibleCharts.length === 0 && !isPending && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[var(--sage-border-strong)] p-16 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-[var(--sage-bg-overlay)]">
            <svg className="h-6 w-6 text-[var(--sage-text-dim)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M3 13h8V3H3v10zM13 21h8V11h-8v10zM13 3v6h8V3h-8zM3 21h8v-6H3v6z" />
            </svg>
          </div>
          <p className="text-base font-semibold text-[var(--sage-text-primary)]">
            Your custom charts will appear here
          </p>
          <p className="text-sm text-[var(--sage-text-dim)]">
            No custom charts yet. Type a request above to generate one.
          </p>
        </div>
      )}
    </div>
  );
}
