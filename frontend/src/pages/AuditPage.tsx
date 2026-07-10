/**
 * frontend/src/pages/AuditPage.tsx
 *
 * Route: /audit/:sessionId
 *
 * Resilience: when Phase 2/3 background pipeline errors or times out,
 * the user is forwarded to /dashboard/:sessionId so they can inspect
 * whatever data was persisted before the failure (FE records, anomalies,
 * partial charts). The user is never left on a dead-end loading screen.
 *
 * pipelineFailed banner: rendered when session.status === "error",
 * which happens when UploadPage forwards here after a Phase 1 failure.
 *
 * stillProcessingPhase1: UploadPage forwards here after a 10-minute
 * timeout REGARDLESS of whether Phase 1 actually finished. If Phase 1
 * is genuinely still running when that timeout fires (e.g. a large file
 * still profiling), session.status will still be "upload" or "processing"
 * and no anomalies will exist yet. Previously this page rendered the
 * empty "Anomaly Review" form regardless, producing a contradictory
 * header/body state (header showed "Uploading" while the body showed
 * "No anomalies detected", as if analysis had finished with a clean
 * result). This page now detects that case explicitly, shows a distinct
 * banner, and polls until the real status resolves.
 */

import React, { useCallback, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import TopBar from "../components/layout/TopBar";
import AnomalyList from "../components/audit/AnomalyList";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorBanner from "../components/shared/ErrorBanner";
import ActivityFeed from "../components/shared/ActivityFeed";
import { completeAnalysis } from "../api/analyze";
import { getSession } from "../api/sessions";
import { useSessionStore } from "../store/sessionStore";
import { useUiStore } from "../store/uiStore";
import type { AnalyzeCompleteResponse } from "../types/api";
import type { UserDecision } from "../types/session";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS  = 600_000;

// How often to re-check session status while Phase 1 is still legitimately
// running in the background (see stillProcessingPhase1 below).
const PHASE1_STALE_REFETCH_MS = 3000;

export default function AuditPage(): React.ReactElement {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const llmProvider = useUiStore((s) => s.llmProvider);

  const setActiveSession  = useSessionStore((s) => s.setActiveSession);
  const setDecision       = useSessionStore((s) => s.setDecision);
  const clearDecisions    = useSessionStore((s) => s.clearDecisions);
  const pendingDecisions  = useSessionStore((s) => s.pendingDecisions);
  const getDecisionsArray = useSessionStore((s) => s.getDecisionsArray);
  const setPollingActive  = useSessionStore((s) => s.setPollingActive);

  useEffect(() => {
    if (sessionId) setActiveSession(sessionId);
  }, [sessionId, setActiveSession]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: Boolean(sessionId),
    refetchOnWindowFocus: false,
    // Keep re-checking while it looks like Phase 1 has not actually
    // finished yet (see stillProcessingPhase1 derivation below), so the
    // page self-corrects once the backend catches up instead of sitting
    // on a stale/contradictory snapshot.
    refetchInterval: (query) => {
      const snapshot = query.state.data;
      if (!snapshot) return false;
      const s = (snapshot as { session: { status: string }; anomalies?: unknown[] })
        .session.status;
      const noAnomaliesYet =
        ((snapshot as { anomalies?: unknown[] }).anomalies?.length ?? 0) === 0;
      const looksUnfinished =
        (s === "upload" || s === "processing") && noAnomaliesYet;
      return looksUnfinished ? PHASE1_STALE_REFETCH_MS : false;
    },
  });

  const session   = data?.session ?? null;
  const anomalies = data?.anomalies ?? [];

  // Phase 1 error: UploadPage forwarded the user here after status === "error"
  const pipelineFailed = session?.status === "error";

  // UploadPage poll loop forwards here on ANY of: status === "audit",
  // status === "error", or a 10-minute timeout. This flag catches the
  // timeout case where Phase 1 was still genuinely running when the
  // timeout fired -- distinct from a real error and from a legitimate
  // "zero anomalies found" result.
  const stillProcessingPhase1 =
    !pipelineFailed &&
    (session?.status === "upload" || session?.status === "processing") &&
    anomalies.length === 0;

  // -------------------------------------------------------------------------
  // Phase 2/3 polling
  // On error or timeout, navigate forward to dashboard so the user can
  // inspect whatever data was persisted before the failure.
  // -------------------------------------------------------------------------
  const startPolling = useCallback(async () => {
    if (!sessionId) return;
    setPollingActive(true);
    const deadline = Date.now() + POLL_TIMEOUT_MS;

    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      const detail = await getSession(sessionId);
      if (!detail) break;
      const { status } = detail.session;

      if (status === "complete") {
        setPollingActive(false);
        navigate(`/dashboard/${sessionId}`);
        return;
      }
      if (status === "error") {
        // Forward to dashboard: it renders whatever was persisted before failure.
        // Never dead-end the user on this page.
        setPollingActive(false);
        navigate(`/dashboard/${sessionId}`);
        return;
      }
    }

    // Timeout: best-effort forward navigation
    setPollingActive(false);
    navigate(`/dashboard/${sessionId}`);
  }, [sessionId, navigate, setPollingActive]);

  // -------------------------------------------------------------------------
  // Submit mutation (Phase 2/3 kickoff)
  // -------------------------------------------------------------------------
  const mutation = useMutation<AnalyzeCompleteResponse, Error, void>({
    mutationFn: async () => {
      if (!sessionId) throw new Error("No session");
      const decisions: UserDecision[] = getDecisionsArray();
      return completeAnalysis(sessionId, decisions);
    },
    onSuccess: () => { clearDecisions(); void startPolling(); },
  });

  const handleSubmit = useCallback(
    (e: React.FormEvent) => { e.preventDefault(); mutation.mutate(); },
    [mutation],
  );

  // -------------------------------------------------------------------------
  // Loading / error shells
  // -------------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col">
          <TopBar title="Loading..." llmProvider={llmProvider} />
          <main className="flex flex-1 items-center justify-center">
            <LoadingSpinner size="lg" />
          </main>
        </div>
    );
  }

  if (isError || !session) {
    return (
      <div className="flex flex-1 flex-col">
          <TopBar title="Error" status="error" llmProvider={llmProvider} />
          <main className="p-6">
            <ErrorBanner
              message={error instanceof Error ? error : "Session not found."}
              variant="error"
            />
          </main>
        </div>
    );
  }

  // -------------------------------------------------------------------------
  // Main render
  // -------------------------------------------------------------------------
  const decidedCount    = Object.keys(pendingDecisions).length;
  const isSubmitting    = mutation.isPending;
  const isPhase2Running = session.status === "processing" && !stillProcessingPhase1;
  const isGenerating    = mutation.isPending || mutation.isSuccess;
  const canSubmit        =
    decidedCount > 0 && !isSubmitting && !isPhase2Running && !stillProcessingPhase1;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          title={session.original_filename}
          status={session.status}
          llmProvider={session.llm_provider}
          breadcrumb={[{ label: "Sessions", href: "/" }, { label: "Anomaly Review" }]}
        />

        <main className="flex-1 overflow-y-auto px-4 py-6 lg:px-8">
          <div className="mx-auto max-w-3xl">
            <div className="mb-5">
              <h2 className="text-xl font-bold text-[var(--sage-text-primary)]">
                Anomaly Review
              </h2>
              <p className="mt-0.5 text-sm text-[var(--sage-text-muted)]">
                {session.row_count && `${session.row_count.toLocaleString()} rows`}
                {session.col_count && ` x ${session.col_count} columns`}
              </p>
            </div>

            {/* Phase 1 still genuinely running (timeout forwarded us here early) */}
            {stillProcessingPhase1 && (
              <div
                aria-live="polite"
                className="mb-4 rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] px-4 py-3"
              >
                <div className="flex items-center gap-2 text-sm text-[var(--sage-accent)]">
                  <span className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-[var(--sage-accent)] border-t-transparent" />
                  Still analyzing this file. Large or wide files can take longer
                  than expected. This page will update automatically when
                  analysis finishes.
                </div>
                {sessionId && <ActivityFeed sessionId={sessionId} />}
              </div>
            )}

            {/* Phase 1 failure banner (forwarded from UploadPage) */}
            {pipelineFailed && (
              <div className="mb-4">
                <ErrorBanner
                  message={
                    session.error_message ??
                    "The analysis pipeline encountered an error. Please try uploading the file again."
                  }
                  variant="error"
                />
              </div>
            )}

            {/* Phase 2/3 running indicator */}
            {(isPhase2Running || isGenerating) && (
              <div
                aria-live="polite"
                className="mb-4 rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] px-4 py-3"
              >
                <div className="flex items-center gap-2 text-sm text-[var(--sage-accent)]">
                  <span className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-[var(--sage-accent)] border-t-transparent" />
                  Cleaning data and generating EDA portfolio...
                </div>
                {sessionId && <ActivityFeed sessionId={sessionId} />}
              </div>
            )}

            {/* Phase 2/3 submission error (HTTP-level failure) */}
            {mutation.isError && (
              <div className="mb-4">
                <ErrorBanner message={mutation.error} variant="error" />
              </div>
            )}

            {!stillProcessingPhase1 && !pipelineFailed && !isGenerating && (
              <form onSubmit={handleSubmit} className="flex flex-col gap-6">
                <AnomalyList
                  anomalies={anomalies}
                  decisions={pendingDecisions}
                  onDecisionChange={setDecision}
                  totalRows={session.row_count}
                />
                {anomalies.length > 0 && !pipelineFailed && (
                  <div className="flex items-center justify-between rounded-xl bg-[var(--sage-bg-elevated)] px-5 py-4 shadow-sm ring-1 ring-[var(--sage-border)]">
                    <p className="text-sm text-[var(--sage-text-muted)]">
                      {decidedCount} / {anomalies.length} decisions made
                    </p>
                    <button
                      type="submit"
                      disabled={!canSubmit}
                      className="rounded-xl bg-[var(--sage-accent)] px-6 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isSubmitting ? "Submitting..." : "Apply Decisions & Generate Report"}
                    </button>
                  </div>
                )}
              </form>
            )}
          </div>
        </main>
      </div>
  );
}
