/**
 * frontend/src/components/dashboard/DownloadsTab.tsx
 *
 * Dashboard tab — download raw / clean / engineered CSVs and audit log.
 */

import React from "react";
import type { Session, AuditLog } from "../../types/session";

interface Props {
  session: Session;
  auditLog: AuditLog[];
}

export default function DownloadsTab({ session, auditLog }: Props): React.ReactElement {
  const files = [
    { label: "Raw upload",     filename: session.stored_filename,        desc: "Original file as uploaded — no modifications." },
    { label: "Clean CSV",      filename: `${session.id}_clean.csv`,      desc: "Post-cleaning output from the Janitor agent." },
    { label: "Engineered CSV", filename: `${session.id}_engineered.csv`, desc: "Feature-engineered output (OHE, log transforms, interaction terms)." },
  ];

  function downloadAuditCsv(): void {
    const headers = ["agent", "phase", "action", "reason", "column", "rows", "llm", "timestamp"];
    const rows = auditLog.map((e) => [
      e.agent_name, e.phase,
      `"${e.action.replace(/"/g, '""')}"`,
      `"${e.reason.replace(/"/g, '""')}"`,
      e.column_affected ?? "",
      e.rows_affected,
      e.is_llm_decision ? "yes" : "no",
      e.timestamp,
    ].join(","));
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `${session.id}_audit_log.csv`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {files.map((f) => (
          <a
            key={f.filename}
            href={`/api/download/${f.filename}`}
            download
            className="flex flex-col gap-2 rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-6 transition-colors hover:border-[var(--sage-accent-border)]"
          >
            <span className="text-sm font-semibold text-[var(--sage-text-primary)]">{f.label}</span>
            <span className="text-xs text-[var(--sage-text-muted)]">{f.desc}</span>
            <span className="mt-1 break-all rounded bg-[var(--sage-accent-soft)] px-2 py-1 font-mono text-xs text-[var(--sage-accent)]">{f.filename}</span>
          </a>
        ))}
      </div>

      <button
        type="button"
        onClick={downloadAuditCsv}
        disabled={auditLog.length === 0}
        className="flex w-full flex-col gap-2 rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-6 text-left transition-colors hover:border-[var(--sage-accent-border)] disabled:cursor-not-allowed disabled:opacity-50 sm:max-w-sm"
      >
        <span className="text-sm font-semibold text-[var(--sage-text-primary)]">Audit Log CSV</span>
        <span className="text-xs text-[var(--sage-text-muted)]">Full agent decision trace — {auditLog.length} entries.</span>
        <span className="mt-1 break-all rounded bg-[var(--sage-accent-soft)] px-2 py-1 font-mono text-xs text-[var(--sage-accent)]">
          {session.id}_audit_log.csv
        </span>
      </button>
    </div>
  );
}
