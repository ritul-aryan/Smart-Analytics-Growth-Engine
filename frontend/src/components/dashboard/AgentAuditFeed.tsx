/**
 * frontend/src/components/dashboard/AgentAuditFeed.tsx
 *
 * Scrollable real-time agent action log for the Audit Log tab.
 *
 * Renders all AuditLog entries for the session in reverse-chronological
 * order.  Each entry shows: agent name, phase badge, action description,
 * reason, column affected, rows affected, LLM decision flag, and timestamp.
 *
 * Supports filtering by agent name and phase via a compact filter bar.
 * A "Download CSV" button triggers GET /api/download/{filename} for the
 * audit log export (handled separately via the sessions endpoint which
 * must expose a download_url).
 *
 * Usage:
 *   <AgentAuditFeed entries={auditLog} sessionId={session.id} />
 */

import React, { useState, useMemo } from "react";
import type { AuditLog } from "../../types/session";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AgentAuditFeedProps {
  entries: AuditLog[];
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

// Categorical agent badges mapped to prototype tokens:
// accent (violet), low (sky), good (green), high (orange), crit (rose).
const AGENT_COLORS: Record<string, string> = {
  orchestrator: "bg-[var(--sage-accent-soft)] text-[var(--sage-accent)]",
  profiler:     "bg-[var(--sage-low-soft)] text-[var(--sage-low)]",
  janitor:      "bg-[var(--sage-good-soft)] text-[var(--sage-good)]",
  engineer:     "bg-[var(--sage-high-soft)] text-[var(--sage-high)]",
  storyteller:  "bg-[var(--sage-crit-soft)] text-[var(--sage-crit)]",
  auditor:      "bg-[var(--sage-bg-overlay)] text-[var(--sage-text-muted)]",
};

const PHASE_LABELS: Record<string, string> = {
  phase1:   "Phase 1",
  phase2:   "Phase 2",
  phase2_5: "Phase 2.5",
  phase3:   "Phase 3",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function agentColor(agent: string): string {
  return AGENT_COLORS[agent.toLowerCase()] ?? "bg-[var(--sage-bg-overlay)] text-[var(--sage-text-muted)]";
}

// ---------------------------------------------------------------------------
// Single entry row
// ---------------------------------------------------------------------------

function AuditEntry({ entry }: { entry: AuditLog }): React.ReactElement {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = Boolean(entry.reason || entry.column_affected || entry.llm_prompt_summary);

  return (
    <div className="border-b border-[var(--sage-border)] px-4 py-3 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        {/* Left: agent + phase + action */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={["rounded-full px-2 py-0.5 text-xs font-medium", agentColor(entry.agent_name)].join(" ")}>
            {entry.agent_name}
          </span>
          {entry.phase && (
            <span className="text-xs text-[var(--sage-text-dim)]">
              {PHASE_LABELS[entry.phase] ?? entry.phase}
            </span>
          )}
          {entry.is_llm_decision && (
            <span className="rounded-full bg-[var(--sage-accent-soft)] px-1.5 py-0.5 text-xs font-medium text-[var(--sage-accent)]">
              LLM
            </span>
          )}
        </div>

        {/* Right: timestamp + rows */}
        <div className="flex items-center gap-3 text-xs text-[var(--sage-text-dim)]">
          {entry.rows_affected > 0 && (
            <span>{entry.rows_affected.toLocaleString()} rows</span>
          )}
          <span className="tabular-nums">{formatTimestamp(entry.timestamp)}</span>
        </div>
      </div>

      {/* Action */}
      <p className="mt-1.5 text-xs font-medium text-[var(--sage-text-primary)]">
        {entry.action}
      </p>

      {/* Column affected */}
      {entry.column_affected && (
        <p className="mt-0.5 font-mono text-xs text-[var(--sage-text-muted)]">
          col: {entry.column_affected}
        </p>
      )}

      {/* Expandable reason */}
      {hasDetail && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-xs text-[var(--sage-accent)] hover:opacity-80"
          >
            {expanded ? "Hide detail ↑" : "Show detail ↓"}
          </button>
          {expanded && (
            <div className="mt-2 rounded-lg bg-[var(--sage-bg-overlay)] p-2.5 text-xs text-[var(--sage-text-muted)]">
              {entry.reason && <p><span className="font-semibold">Reason:</span> {entry.reason}</p>}
              {entry.llm_prompt_summary && (
                <p className="mt-1"><span className="font-semibold">Prompt:</span> {entry.llm_prompt_summary}</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AgentAuditFeed({
  entries,
  className = "",
}: AgentAuditFeedProps): React.ReactElement {
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [phaseFilter, setPhaseFilter] = useState<string>("all");

  const agents = useMemo(
    () => ["all", ...Array.from(new Set(entries.map((e) => e.agent_name)))],
    [entries],
  );
  const phases = useMemo(
    () => ["all", ...Array.from(new Set(entries.map((e) => e.phase)))],
    [entries],
  );

  const filtered = useMemo(
    () => entries.filter(
      (e) =>
        (agentFilter === "all" || e.agent_name === agentFilter) &&
        (phaseFilter === "all" || e.phase === phaseFilter),
    ),
    [entries, agentFilter, phaseFilter],
  );

  const selectClass = [
    "rounded-lg border px-2 py-1 text-xs",
    "border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] text-[var(--sage-text-primary)]",
    "hover:border-[var(--sage-accent-border)] focus:outline-none focus:ring-2 focus:ring-[var(--sage-accent)]",
  ].join(" ");

  return (
    <div
      className={[
        "rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]",
        className,
      ].join(" ")}
    >
      {/* Filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--sage-border)] px-4 py-3">
        <p className="text-sm font-semibold text-[var(--sage-text-primary)]">
          Audit Log
          <span className="ml-2 text-xs font-normal text-[var(--sage-text-dim)]">
            ({filtered.length} of {entries.length})
          </span>
        </p>
        <div className="flex items-center gap-2">
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            aria-label="Filter by agent"
            className={selectClass}
          >
            {agents.map((a) => (
              <option key={a} value={a}>{a === "all" ? "All agents" : a}</option>
            ))}
          </select>
          <select
            value={phaseFilter}
            onChange={(e) => setPhaseFilter(e.target.value)}
            aria-label="Filter by phase"
            className={selectClass}
          >
            {phases.map((p) => (
              <option key={p} value={p}>{p === "all" ? "All phases" : PHASE_LABELS[p] ?? p}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Feed */}
      <div className="max-h-[480px] overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--sage-text-dim)]">
            No audit entries match the current filter.
          </p>
        ) : (
          filtered.map((entry) => <AuditEntry key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  );
}
