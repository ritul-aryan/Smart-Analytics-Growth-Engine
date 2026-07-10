/**
 * frontend/src/components/dashboard/DataHealthPanel.tsx
 *
 * Overview tab — data quality panels beneath the narrative.
 *
 * Layout:
 *   Row 1: stat strip (rows / cols / file / status)
 *   Row 2: quality score gauges (half-circle SVG arcs) + anomaly notes
 *   Row 3: missingness heatmap (if any)
 *   Row 4: correlation panel (if any)
 *   Row 5: column stats table
 */

import React from "react";
import QualityScoreGauge from "./QualityScoreGauge";
import ColumnStatsTable from "./ColumnStatsTable";
import MissingnessHeatmap from "./MissingnessHeatmap";
import CorrelationPanel from "./CorrelationPanel";
import type { Session } from "../../types/session";
import type { EdaNarrative } from "../../types/chart";

interface DataHealthPanelProps {
  session: Session;
  narrative: EdaNarrative | null;
  className?: string;
}

// ---------------------------------------------------------------------------
// Stat strip
// ---------------------------------------------------------------------------

function StatStrip({ session }: { session: Session }): React.ReactElement {
  const items = [
    { label: "Rows",    value: session.row_count != null ? session.row_count.toLocaleString() : "—" },
    { label: "Columns", value: session.col_count != null ? String(session.col_count) : "—" },
    { label: "File",    value: session.original_filename ?? "—" },
    { label: "Status",  value: session.status },
  ];
  return (
    <div className="flex flex-wrap gap-3">
      {items.map((item) => (
        <div key={item.label} className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] px-4 py-3">
          <p className="text-xs text-[var(--sage-text-muted)]">{item.label}</p>
          <p className="mt-0.5 text-sm font-semibold text-[var(--sage-text-primary)]">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Anomaly notes card
// ---------------------------------------------------------------------------

function AnomalyCard({ notes }: { notes: string[] }): React.ReactElement | null {
  if (notes.length === 0) return null;
  return (
    <div className="rounded-xl border border-[var(--sage-high)] bg-[var(--sage-high-soft)] p-5">
      <div className="mb-3 flex items-center gap-2">
        <svg className="h-4 w-4 text-[var(--sage-high)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
        </svg>
        <h4 className="text-sm font-semibold text-[var(--sage-high)]">Anomalies &amp; Insights</h4>
      </div>
      <ul className="space-y-1.5">
        {notes.map((note, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-[var(--sage-text-muted)]">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--sage-high)]" />
            {note}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function DataHealthPanel({
  session,
  narrative,
  className = "",
}: DataHealthPanelProps): React.ReactElement {
  const colStats     = narrative?.column_stats         ?? [];
  const hotspots     = narrative?.missingness_hotspots ?? [];
  const correlations = narrative?.top_correlations     ?? [];
  const anomalyNotes = narrative?.anomaly_notes        ?? [];

  return (
    <div className={["space-y-5", className].join(" ")}>

      <StatStrip session={session} />

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-5">
          <h3 className="mb-4 text-sm font-semibold text-[var(--sage-text-primary)]">Data Quality Score</h3>
          <QualityScoreGauge
            before={session.quality_score_before ?? 0}
            after={session.quality_score_after ?? null}
          />
        </div>
        {anomalyNotes.length > 0 && (
          <div className="sm:col-span-1 lg:col-span-2">
            <AnomalyCard notes={anomalyNotes} />
          </div>
        )}
      </div>

      {hotspots.length > 0 && <MissingnessHeatmap hotspots={hotspots} />}

      {correlations.length > 0 && <CorrelationPanel correlations={correlations} />}

      {colStats.length > 0 ? (
        <ColumnStatsTable columns={colStats} />
      ) : (
        <div className="rounded-xl border border-dashed border-[var(--sage-border-strong)] p-8 text-center">
          <p className="text-sm text-[var(--sage-text-muted)]">
            Column statistics will appear here after the analysis pipeline completes.
          </p>
        </div>
      )}

    </div>
  );
}
