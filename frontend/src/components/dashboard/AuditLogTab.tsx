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
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--sage-border)] text-left">
              {["Agent", "Phase", "Action", "Reason", "Column", "Rows", "Time"].map((h) => (
                <th key={h} className="px-4 py-3 font-medium text-[var(--sage-text-muted)]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.map((log, i) => (
              <tr key={log.id} className={["border-b border-[var(--sage-border)]", i % 2 !== 0 ? "bg-[var(--sage-bg-overlay)]" : ""].join(" ")}>
                <td className="px-4 py-2.5 font-mono text-[var(--sage-accent)]">{log.agent_name}</td>
                <td className="px-4 py-2.5 text-[var(--sage-text-primary)]">{log.phase}</td>
                <td className="max-w-[200px] truncate px-4 py-2.5 text-[var(--sage-text-primary)]" title={log.action}>{log.action}</td>
                <td className="max-w-[200px] truncate px-4 py-2.5 text-[var(--sage-text-muted)]" title={log.reason}>{log.reason}</td>
                <td className="px-4 py-2.5 font-mono text-[var(--sage-text-muted)]">{log.column_affected ?? "—"}</td>
                <td className="px-4 py-2.5 tabular-nums text-[var(--sage-text-primary)]">{log.rows_affected.toLocaleString()}</td>
                <td className="px-4 py-2.5 tabular-nums text-[var(--sage-text-muted)]">{new Date(log.timestamp).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
