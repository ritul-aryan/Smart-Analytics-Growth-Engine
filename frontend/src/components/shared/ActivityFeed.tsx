/**
 * frontend/src/components/shared/ActivityFeed.tsx
 *
 * Live activity ticker shown under loading spinners during Phase 1 and
 * Phase 2/3 processing.
 *
 * Polls GET /api/session/{id} every POLL_MS milliseconds, extracts the
 * most recent audit_log entries written by the backend agents, and renders
 * them as a compact feed so the user can see real work happening rather
 * than just a generic spinner.
 *
 * Rendered text format:
 *   Profiler:    Detected 234 missing values in "price"
 *   Janitor:     Imputed median value for column "price"
 *   Engineer:    Applied log transform to "revenue"
 *   Storyteller: Generated scatter plot for "price" vs "revenue"
 *
 * Design decisions:
 * - Self-contained polling loop (useEffect + setTimeout chain) so the
 *   parent does not need to share its own poll timer.
 * - Returns null until at least one entry exists — callers need no
 *   conditional guards.
 * - MAX_VISIBLE = 4: shows context without overwhelming the overlay.
 * - Older entries fade to 40% opacity so the eye is drawn to the newest.
 */

import React, { useEffect, useRef, useState } from "react";
import { getSession } from "../../api/sessions";
import type { AuditLog } from "../../types/session";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const POLL_MS       = 1500;
const MAX_VISIBLE   = 4;

/** Maps backend agent_name values to display-friendly labels. */
const AGENT_LABEL: Record<string, string> = {
  profiler:       "Profiler",
  janitor:        "Janitor",
  engineer:       "Engineer",
  storyteller:    "Storyteller",
  orchestrator:   "Orchestrator",
  validator:      "Validator",
};

function labelFor(name: string): string {
  return (
    AGENT_LABEL[name.toLowerCase()] ??
    name.charAt(0).toUpperCase() + name.slice(1)
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  /** Session UUID to poll for audit_log entries. */
  sessionId: string;
}

export default function ActivityFeed({ sessionId }: Props): React.ReactElement | null {
  const [entries, setEntries] = useState<AuditLog[]>([]);
  const timerRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;

    async function tick(): Promise<void> {
      try {
        const detail = await getSession(sessionId);
        if (!activeRef.current) return;
        if (detail && Array.isArray(detail.audit_log)) {
          const sorted = [...detail.audit_log].sort(
            (a, b) =>
              new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
          );
          setEntries(sorted.slice(-MAX_VISIBLE));
        }
      } catch {
        // Swallow: the parent polling loop owns error state
      }
      if (activeRef.current) {
        timerRef.current = setTimeout(() => { void tick(); }, POLL_MS);
      }
    }

    void tick();

    return () => {
      activeRef.current = false;
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, [sessionId]);

  if (entries.length === 0) return null;

  return (
    <div
      className="mt-3 space-y-1.5"
      aria-live="polite"
      aria-label="Pipeline activity"
    >
      {entries.map((entry, idx) => {
        const isLatest = idx === entries.length - 1;
        return (
          <div
            key={entry.id}
            className={[
              "flex items-start gap-2 text-xs font-mono transition-opacity duration-300",
              isLatest ? "opacity-100" : "opacity-40",
            ].join(" ")}
          >
            {/* Status dot */}
            {isLatest ? (
              <span
                className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[var(--sage-accent)]"
                aria-hidden="true"
              />
            ) : (
              <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--sage-border)]" aria-hidden="true" />
            )}

            {/* Message */}
            <p className={isLatest ? "text-[var(--sage-text-primary)]" : "text-[var(--sage-text-muted)]"}>
              <span className="font-semibold">{labelFor(entry.agent_name)}</span>
              <span className="text-[var(--sage-text-muted)]">: </span>
              {entry.action}
            </p>
          </div>
        );
      })}
    </div>
  );
}
