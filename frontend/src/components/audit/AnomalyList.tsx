/**
 * frontend/src/components/audit/AnomalyList.tsx
 *
 * Renders all anomaly cards sorted by display_order.
 * Provides a summary count by severity above the list.
 */

import AnomalyCard from "./AnomalyCard";
import type { Anomaly, UserDecision } from "../../types/session";

interface AnomalyListProps {
  anomalies: Anomaly[];
  decisions: Record<string, UserDecision>;
  onDecisionChange: (decision: UserDecision) => void;
  totalRows: number | null;
}

export default function AnomalyList({
  anomalies,
  decisions,
  onDecisionChange,
  totalRows,
}: AnomalyListProps): React.ReactElement {
  if (anomalies.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--sage-good)] bg-[var(--sage-good-soft)] px-6 py-10 text-center">
        <p className="text-lg font-semibold text-[var(--sage-good)]">No anomalies detected</p>
        <p className="mt-1 text-sm text-[var(--sage-good)]">
          This dataset passed all 5 detection tiers cleanly.
        </p>
      </div>
    );
  }

  const sorted = [...anomalies].sort((a, b) => a.display_order - b.display_order);

  const high   = anomalies.filter((a) => a.severity === "high").length;
  const medium = anomalies.filter((a) => a.severity === "medium").length;
  const low    = anomalies.filter((a) => a.severity === "low").length;
  const decided = Object.keys(decisions).length;

  return (
    <div className="flex flex-col gap-4">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg bg-[var(--sage-bg-overlay)] px-4 py-3 text-sm">
        <span className="font-medium text-[var(--sage-text-primary)]">
          {anomalies.length} anomalies
        </span>
        {high > 0 && (
          <span className="rounded-full bg-[var(--sage-crit-soft)] px-2 py-0.5 text-xs font-semibold text-[var(--sage-crit)]">
            {high} high
          </span>
        )}
        {medium > 0 && (
          <span className="rounded-full bg-[var(--sage-high-soft)] px-2 py-0.5 text-xs font-semibold text-[var(--sage-high)]">
            {medium} medium
          </span>
        )}
        {low > 0 && (
          <span className="rounded-full bg-[var(--sage-low-soft)] px-2 py-0.5 text-xs font-semibold text-[var(--sage-low)]">
            {low} low
          </span>
        )}
        <span className="ml-auto text-[var(--sage-text-muted)]">
          {decided} / {anomalies.length} decisions made
        </span>
      </div>

      {/* Cards */}
      {sorted.map((anomaly) => (
        <AnomalyCard
          key={anomaly.id}
          anomaly={anomaly}
          decision={decisions[anomaly.id]}
          onDecisionChange={onDecisionChange}
          totalRows={totalRows}
        />
      ))}
    </div>
  );
}
