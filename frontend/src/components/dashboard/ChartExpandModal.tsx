/**
 * frontend/src/components/dashboard/ChartExpandModal.tsx
 *
 * Full-screen expanded view for a single chart. Purely additive/display —
 * no data fetching, no mutations. Opened/closed via parent-owned state.
 */

import React, { useEffect } from "react";
import PlotlyChart from "./PlotlyChart";
import type { ChartSpec } from "../../types/chart";

interface ChartExpandModalProps {
  chart: ChartSpec;
  onClose: () => void;
}

export default function ChartExpandModal({
  chart,
  onClose,
}: ChartExpandModalProps): React.ReactElement {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/70"
      onClick={onClose}
    >
      <div
        className="mx-auto my-8 max-w-6xl max-h-[90vh] overflow-y-auto rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--sage-border)] px-5 py-4">
          <h2 className="truncate text-base font-semibold text-[var(--sage-text-primary)]">
            {chart.title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--sage-text-muted)] hover:bg-[var(--sage-bg-overlay)] hover:text-[var(--sage-text-primary)]"
          >
            <svg className="h-4 w-4" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">
              <path d="M3.22 3.22a.75.75 0 011.06 0L7 5.94l2.72-2.72a.75.75 0 111.06 1.06L8.06 7l2.72 2.72a.75.75 0 11-1.06 1.06L7 8.06l-2.72 2.72a.75.75 0 01-1.06-1.06L5.94 7 3.22 4.28a.75.75 0 010-1.06z" />
            </svg>
          </button>
        </div>
        <div className="p-5">
          <PlotlyChart
            chart={chart}
            height={Math.round(window.innerHeight * 0.6)}
            showExport
            insightMode="full"
          />
        </div>
      </div>
    </div>
  );
}
