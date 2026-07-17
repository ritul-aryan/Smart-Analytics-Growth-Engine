/**
 * frontend/src/components/shared/SessionHistory.tsx
 *
 * Past sessions list rendered in the sidebar.
 *
 * Navigation rules (status -> route):
 *   complete, error  ->  /dashboard/:id  (error shows the error banner there)
 *   everything else  ->  /audit/:id      (audit, processing, upload, review)
 *
 * Delete:
 *   Trash icon on each card (visible on hover) calls
 *   DELETE /api/sessions/:id.  All child rows are removed via DB cascade.
 *   If the deleted session is currently active, navigates to / and clears
 *   the Zustand active session so the user lands on a clean UploadPage.
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteSession, getSessions } from "../../api/sessions";
import { useSessionStore } from "../../store/sessionStore";
import type { Session, SessionStatus } from "../../types/session";

// ---------------------------------------------------------------------------
// Status presentation maps
// ---------------------------------------------------------------------------

const STATUS_DOT: Record<SessionStatus, string> = {
  upload:     "bg-[var(--sage-text-dim)]",
  audit:      "bg-[var(--sage-good)]",
  processing: "bg-[var(--sage-low)] animate-pulse",
  complete:   "bg-[var(--sage-good)]",
  error:      "bg-[var(--sage-crit)]",
};

const STATUS_LABEL: Record<SessionStatus, string> = {
  upload:     "Uploading",
  audit:      "Review ready",
  processing: "Processing...",
  complete:   "Complete",
  error:      "Error",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  try {
    // Backend emits UTC timestamps. If the string carries no timezone
    // marker, append "Z" so it is parsed as UTC and toLocale* converts it
    // to the viewer's local time automatically.
    const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
    const normalized = hasTz ? iso : `${iso}Z`;
    return new Date(normalized).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function sessionPath(session: Session): string {
  const s = (session.status?.toLowerCase() ?? "upload") as SessionStatus;
  // complete and error both land on the dashboard (error shows its banner there)
  if (s === "complete" || s === "error") {
    return `/dashboard/${session.id}`;
  }
  // audit, review, processing, upload -> audit page
  return `/audit/${session.id}`;
}

// ---------------------------------------------------------------------------
// Trash icon
// ---------------------------------------------------------------------------

function TrashIcon(): React.ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor" aria-hidden="true">
      <path d="M6.5 1h3a.5.5 0 0 1 .5.5v1H6v-1a.5.5 0 0 1 .5-.5ZM11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3A1.5 1.5 0 0 0 5 1.5v1H1.5a.5.5 0 0 0 0 1h.538l.853 10.66A2 2 0 0 0 4.885 16h6.23a2 2 0 0 0 1.994-1.84l.853-10.66H14.5a.5.5 0 0 0 0-1H11zm1.958 1-.846 10.58a1 1 0 0 1-.997.92h-6.23a1 1 0 0 1-.997-.92L3.042 3.5h9.916zm-7.487 1a.5.5 0 0 1 .528.47l.5 8.5a.5.5 0 0 1-.998.06L5 5.03a.5.5 0 0 1 .47-.53zm5.058 0a.5.5 0 0 1 .47.53l-.5 8.5a.5.5 0 1 1-.998-.06l.5-8.5a.5.5 0 0 1 .528-.47zM8 4.5a.5.5 0 0 1 .5.5v8.5a.5.5 0 0 1-1 0V5a.5.5 0 0 1 .5-.5z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Session card
// ---------------------------------------------------------------------------

interface SessionCardProps {
  session: Session;
  onDeleteSuccess: (sessionId: string) => void;
}

function SessionCard({ session, onDeleteSuccess }: SessionCardProps): React.ReactElement {
  const navigate     = useNavigate();
  const normalStatus = (session.status?.toLowerCase() ?? "upload") as SessionStatus;
  const dot          = STATUS_DOT[normalStatus]   ?? "bg-[var(--sage-text-dim)]";
  const label        = STATUS_LABEL[normalStatus] ?? session.status;

  const deleteMutation = useMutation({
    mutationFn: () => deleteSession(session.id),
    onSuccess: () => onDeleteSuccess(session.id),
  });

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteMutation.mutate();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      navigate(sessionPath(session));
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => navigate(sessionPath(session))}
      onKeyDown={handleKeyDown}
      className="group relative w-full cursor-pointer rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] px-3 py-2.5 text-left transition-colors hover:border-[var(--sage-accent-border)] hover:bg-[var(--sage-bg-overlay)]"
    >
      {/* Top row: filename, status dot, delete button */}
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-xs font-medium text-[var(--sage-text-primary)]">
          {session.original_filename}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={["mt-0.5 h-2 w-2 rounded-full", dot].join(" ")}
            title={label}
          />
          {/* Trash button: hidden until card is hovered */}
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            aria-label={`Delete ${session.original_filename}`}
            className="mt-0.5 hidden text-[var(--sage-text-dim)] transition-colors hover:text-[var(--sage-crit)] disabled:opacity-50 group-hover:block"
          >
            {deleteMutation.isPending ? (
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border border-current border-t-transparent" />
            ) : (
              <TrashIcon />
            )}
          </button>
        </div>
      </div>

      {/* Status + date */}
      <div className="mt-1 flex items-center justify-between gap-1">
        <span className="text-xs text-[var(--sage-text-muted)]">{label}</span>
        <span className="text-xs text-[var(--sage-text-muted)]">{formatDate(session.created_at)}</span>
      </div>

      {/* Intent preview */}
      {session.user_intent && (
        <p className="mt-1 truncate text-xs italic text-[var(--sage-text-muted)]">
          &ldquo;{session.user_intent}&rdquo;
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SessionHistory(): React.ReactElement {
  const navigate         = useNavigate();
  const activeSessionId  = useSessionStore((s) => s.activeSessionId);
  const clearActiveSession = useSessionStore((s) => s.clearActiveSession);
  const queryClient      = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => getSessions(20, 0),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });

  const handleDeleteSuccess = (deletedId: string) => {
    // Remove the deleted session from both caches
    void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    void queryClient.removeQueries({ queryKey: ["session", deletedId] });

    // If it was the active session, return the user to the upload page
    if (activeSessionId === deletedId) {
      clearActiveSession();
      navigate("/");
    }
  };

  if (isLoading) {
    return (
      <div className="px-3 py-4 text-center text-xs text-[var(--sage-text-muted)]">
        Loading sessions...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="px-3 py-2 text-center">
        <p className="text-xs text-[var(--sage-crit)]">Failed to load history.</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="mt-1 text-xs text-[var(--sage-accent)] underline hover:opacity-80"
        >
          Retry
        </button>
      </div>
    );
  }

  const sessions = data?.sessions ?? [];

  if (sessions.length === 0) {
    return (
      <p className="px-3 py-4 text-center text-xs text-[var(--sage-text-muted)]">
        No sessions yet. Upload a file to get started.
      </p>
    );
  }

  return (
    <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-2">
      {sessions.map((s) => (
        <SessionCard
          key={s.id}
          session={s}
          onDeleteSuccess={handleDeleteSuccess}
        />
      ))}
    </div>
  );
}
