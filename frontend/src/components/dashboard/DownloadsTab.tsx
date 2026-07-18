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

function FileIcon(): React.ReactElement {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M14 3v4a1 1 0 001 1h4" stroke="var(--sage-accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 3h9l5 5v11a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" stroke="var(--sage-accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DownloadIcon(): React.ReactElement {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3v12M12 15l-4-4M12 15l4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
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

  const linkFiles = files.map((f) => ({ ...f, href: `/api/download/${f.filename}` }));

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]">
      <div className="border-b border-[var(--sage-border)] px-5 py-4">
        <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">Downloads</h3>
        <p className="text-xs text-[var(--sage-text-muted)]">Generated artifacts from this analysis run.</p>
      </div>
      <div className="divide-y divide-[var(--sage-border)]">
        {linkFiles.map((f) => (
          <div key={f.filename} className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-[var(--sage-bg-overlay)]">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent-soft)]">
              <FileIcon />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-[var(--sage-text-primary)]">{f.label}</p>
              <p className="text-xs text-[var(--sage-text-muted)]">{f.desc}</p>
              <p className="mt-1 truncate text-xs text-[var(--sage-text-dim)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{f.filename}</p>
            </div>
            <a
              href={f.href}
              download
              className="flex shrink-0 items-center gap-2 rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-overlay)] px-3.5 py-2 text-xs font-medium text-[var(--sage-text-primary)] transition-colors hover:border-[var(--sage-accent-border)]"
            >
              <DownloadIcon />
              Download
            </a>
          </div>
        ))}
        <div className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-[var(--sage-bg-overlay)]">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent-soft)]">
            <FileIcon />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-[var(--sage-text-primary)]">Audit Log CSV</p>
            <p className="text-xs text-[var(--sage-text-muted)]">Full agent decision trace — {auditLog.length} entries.</p>
            <p className="mt-1 truncate text-xs text-[var(--sage-text-dim)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{session.id}_audit_log.csv</p>
          </div>
          <button
            type="button"
            onClick={downloadAuditCsv}
            disabled={auditLog.length === 0}
            className="flex shrink-0 items-center gap-2 rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-overlay)] px-3.5 py-2 text-xs font-medium text-[var(--sage-text-primary)] transition-colors hover:border-[var(--sage-accent-border)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <DownloadIcon />
            Download
          </button>
        </div>
      </div>
    </div>
  );
}
