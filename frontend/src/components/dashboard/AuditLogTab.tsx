/**
 * frontend/src/components/dashboard/AuditLogTab.tsx
 *
 * Dashboard tab — full agent decision audit trail.
 */

import React from "react";
import type { AuditLog } from "../../types/session";

interface Props {
  logs: AuditLog[];
}

export default function AuditLogTab({ logs }: Props): React.ReactElement {
  if (logs.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-12 text-center">
        <p className="text-sm text-[var(--sage-text-muted)]">No audit entries for this session.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]">
      <div className="flex items-center gap-3 border-b border-[var(--sage-border)] px-5 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent-soft)]">
          <svg className="h-4 w-4 text-[var(--sage-accent)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h3.5a.75.75 0 000-1.5h-2.75V5z" clipRule="evenodd" />
          </svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">Full Agent Action Trail</h3>
          <p className="text-xs text-[var(--sage-text-muted)]">{logs.length} {logs.length === 1 ? "entry" : "entries"} across the analysis pipeline</p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--sage-border)] text-left">
              {["Agent", "Phase", "Action", "Reason", "Column", "Rows", "Time"].map((h) => (
                <th key={h} className="px-4 py-3 font-medium uppercase tracking-wide text-[var(--sage-text-dim)]" style={{ fontSize: "10.5px" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.map((log, i) => (
              <tr
                key={log.id}
                className={[
                  "border-b border-[var(--sage-border)] transition-colors hover:bg-[var(--sage-bg-overlay)]",
                  i % 2 !== 0 ? "bg-[var(--sage-bg-overlay)]/40" : "",
                ].join(" ")}
              >
                <td className="px-4 py-2.5 font-semibold" style={{ fontFamily: "var(--sage-font-mono)", color: "var(--sage-accent)" }}>{log.agent_name}</td>
                <td className="px-4 py-2.5 text-[var(--sage-text-primary)]">{log.phase}</td>
                <td className="max-w-[200px] truncate px-4 py-2.5 text-[var(--sage-text-primary)]" title={log.action}>{log.action}</td>
                <td className="max-w-[200px] truncate px-4 py-2.5 text-[var(--sage-text-muted)]" title={log.reason}>{log.reason}</td>
                <td className="px-4 py-2.5 text-[var(--sage-text-muted)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{log.column_affected ?? "—"}</td>
                <td className="px-4 py-2.5 tabular-nums text-[var(--sage-text-primary)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{log.rows_affected.toLocaleString()}</td>
                <td className="px-4 py-2.5 tabular-nums text-[var(--sage-text-muted)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{new Date(log.timestamp).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
