/**
 * frontend/src/pages/UploadPage.tsx
 *
 * Route: /
 *
 * Entry point for new analyses. Renders the file drop zone and intent
 * input, calls POST /api/analyze/start on submit, then polls
 * GET /api/session/{id} until status transitions to "audit" before
 * navigating to /audit/:sessionId.
 *
 * Resilience: on Phase 1 error OR timeout the user is forwarded to
 * /audit/:sessionId anyway. AuditPage renders a pipelineFailed banner
 * when session.status === "error", so the user is never dead-ended.
 *
 * State is local; no Zustand writes until session_id is obtained.
 */

import React, { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";

import FileDropZone from "../components/upload/FileDropZone";
import IntentInput from "../components/upload/IntentInput";
import ActivityFeed from "../components/shared/ActivityFeed";
import { startAnalysis } from "../api/analyze";
import { getSession } from "../api/sessions";
import { useSessionStore } from "../store/sessionStore";
import { useUiStore } from "../store/uiStore";
import type { AnalyzeStartResponse } from "../types/api";
import AnalysisSettingsPanel from "../components/upload/AnalysisSettingsPanel";

// ---------------------------------------------------------------------------
// Polling config
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 600_000; // 10 min hard stop (accommodates slow SLM fallback)

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function UploadPage(): React.ReactElement {
  const navigate = useNavigate();
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setPollingActive = useSessionStore((s) => s.setPollingActive);
  const llmProvider      = useUiStore((s) => s.llmProvider);
  const analysisSettings = useUiStore((s) => s.analysisSettings);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [intent, setIntent] = useState("");
  const [pollStatus, setPollStatus] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  /** Session ID received from the backend after POST /api/analyze/start.
   *  Set here (in addition to sessionStore) so ActivityFeed can be mounted
   *  while UploadPage is still visible and polling. */
  const [liveSessionId, setLiveSessionId] = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // Polling loop
  // -------------------------------------------------------------------------

  const startPolling = useCallback(
    async (sessionId: string) => {
      setPollingActive(true);
      const deadline = Date.now() + POLL_TIMEOUT_MS;

      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

        const detail = await getSession(sessionId);
        if (!detail) {
          // Network / server error: stay on upload page with a message
          setPollStatus(null);
          setPollError("Could not reach the server. Check your connection and try again.");
          setPollingActive(false);
          return;
        }

        const { status } = detail.session;
        setPollStatus(status);

        if (status === "audit") {
          setPollingActive(false);
          navigate(`/audit/${sessionId}`);
          return;
        }

        if (status === "error") {
          // Forward to AuditPage regardless; it renders a pipelineFailed banner.
          // This ensures the user can inspect any anomalies that were persisted
          // before the failure and is never left on a dead-end loading screen.
          setPollingActive(false);
          setPollStatus(null);
          navigate(`/audit/${sessionId}`);
          return;
        }
      }

      // Timeout: best-effort forward navigation; AuditPage handles partial state
      setPollingActive(false);
      setPollStatus(null);
      navigate(`/audit/${sessionId}`);
    },
    [navigate, setPollingActive],
  );

  // -------------------------------------------------------------------------
  // Submit mutation
  // -------------------------------------------------------------------------

  const mutation = useMutation<AnalyzeStartResponse, Error, void>({
    mutationFn: async () => {
      if (!selectedFile) throw new Error("No file selected");
      return startAnalysis(selectedFile, intent, llmProvider, analysisSettings);
    },
    onSuccess: (data) => {
      setActiveSession(data.session_id);
      setLiveSessionId(data.session_id);
      setPollStatus("upload");
      void startPolling(data.session_id);
    },
    onError: (err) => {
      setPollError(err.message);
    },
  });

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setPollError(null);
      mutation.mutate();
    },
    [mutation],
  );

  // -------------------------------------------------------------------------
  // Derived state
  // -------------------------------------------------------------------------

  const isLoading = mutation.isPending || pollStatus === "upload";
  const canSubmit = selectedFile !== null && !isLoading;

  const statusLabel: Record<string, string> = {
    upload:     "Uploading file and starting analysis...",
    processing: "Running anomaly detection and profiling...",
    audit:      "Analysis complete, loading audit view...",
    error:      "Forwarding to audit view...",
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <main className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-12">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-[var(--sage-text-primary)]">
            SAGE Data Analytics
          </h1>
          <p className="mt-2 text-[var(--sage-text-muted)]">
            Upload a CSV or Excel file to detect anomalies and generate an EDA
            portfolio.
          </p>
        </div>

        {/* Upload form */}
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-6 rounded-2xl bg-[var(--sage-bg-elevated)] p-8 shadow-sm ring-1 ring-[var(--sage-border)]"
          aria-label="File upload form"
        >
          <FileDropZone
            selectedFile={selectedFile}
            onFileSelected={setSelectedFile}
            onFileCleared={() => setSelectedFile(null)}
            disabled={isLoading}
          />

          <IntentInput
            value={intent}
            onChange={setIntent}
            disabled={isLoading}
          />

          <AnalysisSettingsPanel disabled={isLoading} />

          {/* Error banner */}
          {pollError && (
            <div
              role="alert"
              className="rounded-lg border border-[var(--sage-crit)] bg-[var(--sage-crit-soft)] px-4 py-3 text-sm text-[var(--sage-crit)]"
            >
              {pollError}
            </div>
          )}

          {/* Status indicator + live activity feed */}
          {isLoading && pollStatus && (
            <div aria-live="polite" className="rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-base)] px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-[var(--sage-accent)]">
                <span className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-[var(--sage-accent)] border-t-transparent" />
                {statusLabel[pollStatus] ?? "Processing..."}
              </div>
              {liveSessionId && (
                <ActivityFeed sessionId={liveSessionId} />
              )}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full rounded-xl bg-[var(--sage-accent)] py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? "Analysing..." : "Start Analysis"}
          </button>
        </form>
      </div>
    </main>
  );
}
