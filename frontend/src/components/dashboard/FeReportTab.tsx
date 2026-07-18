/**
 * frontend/src/components/dashboard/FeReportTab.tsx
 *
 * Dashboard tab — Feature Engineering Report.
 * Displays a summary of OHE / log / datetime / interaction transforms
 * applied by the engineer agent, plus the ML readiness score from the
 * EDA narrative.
 */

import React from "react";
import type { AuditLog } from "../../types/session";
import type { EdaNarrative } from "../../types/chart";

const TRANSFORM_COLOURS: Record<string, string> = {
  OHE:                 "bg-[var(--sage-accent-soft)] text-[var(--sage-accent)]",
  FREQUENCY_ENCODING:  "bg-[var(--sage-med-soft)] text-[var(--sage-med)]",
  LOG_TRANSFORM:       "bg-[var(--sage-low-soft)] text-[var(--sage-low)]",
  DATETIME_EXTRACTION: "bg-[var(--sage-good-soft)] text-[var(--sage-good)]",
  DURATION:            "bg-[var(--sage-good-soft)] text-[var(--sage-good)]",
  INTERACTION_TERM:    "bg-[var(--sage-high-soft)] text-[var(--sage-high)]",
};

const TRANSFORM_FALLBACK = "bg-[var(--sage-bg-overlay)] text-[var(--sage-text-muted)]";

const TYPE_ORDER = [
  "OHE",
  "FREQUENCY_ENCODING",
  "LOG_TRANSFORM",
  "DATETIME_EXTRACTION",
  "DURATION",
  "INTERACTION_TERM",
];

interface Props {
  feEntries: AuditLog[];
  narrative: EdaNarrative | null;
}

export default function FeReportTab({ feEntries, narrative }: Props): React.ReactElement {
  if (feEntries.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-12 text-center">
        <p className="text-sm text-[var(--sage-text-muted)]">No feature engineering transforms were applied for this session.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {TYPE_ORDER.map((t) => {
          const count = feEntries.filter((e) => e.reason === t).length;
          if (count === 0) return null;
          return (
            <span
              key={t}
              className={["rounded-full px-3 py-1 text-[10.5px] font-bold uppercase", TRANSFORM_COLOURS[t] ?? TRANSFORM_FALLBACK].join(" ")}
              style={{ letterSpacing: "0.05em" }}
            >
              {count} {t.replace("_", " ").toLowerCase()}
            </span>
          );
        })}
      </div>
      <div className="overflow-hidden rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]">
        <div className="border-b border-[var(--sage-border)] px-5 py-4">
          <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">Transform Log</h3>
          <p className="text-xs text-[var(--sage-text-muted)]">{feEntries.length} transform{feEntries.length === 1 ? "" : "s"} applied by the Feature Engineering agent</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--sage-border)] text-left">
                {["Type", "Description", "Column", "Rows", "Time"].map((h) => (
                  <th key={h} className="px-4 py-3 font-medium uppercase tracking-wide text-[var(--sage-text-dim)]" style={{ fontSize: "10.5px" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {feEntries.map((e, i) => (
                <tr key={e.id} className={["border-b border-[var(--sage-border)] transition-colors hover:bg-[var(--sage-bg-overlay)]", i % 2 !== 0 ? "bg-[var(--sage-bg-overlay)]/40" : ""].join(" ")}>
                  <td className="px-4 py-2.5">
                    <span
                      className={["rounded px-2 py-0.5 text-[10px] font-bold uppercase", TRANSFORM_COLOURS[e.reason] ?? TRANSFORM_FALLBACK].join(" ")}
                      style={{ fontFamily: "var(--sage-font-mono)", letterSpacing: "0.04em" }}
                    >
                      {e.reason}
                    </span>
                  </td>
                  <td className="max-w-[300px] truncate px-4 py-2.5 text-[var(--sage-text-primary)]" title={e.action}>{e.action}</td>
                  <td className="px-4 py-2.5 text-[var(--sage-text-muted)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{e.column_affected ?? "—"}</td>
                  <td className="px-4 py-2.5 tabular-nums text-[var(--sage-text-primary)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{e.rows_affected.toLocaleString()}</td>
                  <td className="px-4 py-2.5 tabular-nums text-[var(--sage-text-muted)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{new Date(e.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {narrative && (
        <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">ML Readiness Score</h3>
            <span className={[
              "text-xl font-bold tabular-nums",
              narrative.ml_readiness_score >= 80 ? "text-[var(--sage-good)]"
                : narrative.ml_readiness_score >= 50 ? "text-[var(--sage-high)]" : "text-[var(--sage-crit)]",
            ].join(" ")} style={{ fontFamily: "var(--sage-font-mono)" }}>
              {narrative.ml_readiness_score.toFixed(1)}
              <span className="text-sm font-normal text-[var(--sage-text-muted)]"> / 100</span>
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--sage-bg-overlay)]">
            <div className="h-full rounded-full bg-[var(--sage-accent)] transition-all" style={{ width: `${Math.min(100, narrative.ml_readiness_score)}%` }} />
          </div>
          {narrative.ml_readiness_notes.length > 0 && (
            <ul className="mt-3 space-y-1">
              {narrative.ml_readiness_notes.map((n, i) => (
                <li key={i} className="flex gap-2 text-xs text-[var(--sage-high)]"><span aria-hidden="true">⚠</span>{n}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
