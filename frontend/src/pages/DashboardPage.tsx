/**
 * frontend/src/pages/DashboardPage.tsx
 *
 * Route: /dashboard/:sessionId
 * Seven tabs with framer-motion fade-in-slide-up transitions.
 *
 * Tab state:
 *   activeTab lives in sessionStore keyed by sessionId so navigating
 *   away and back restores the last-viewed tab.
 *   useQuery staleTime=5min prevents a loading flash on remount.
 *
 * Polling:
 *   If the page is reached while session.status is "processing" or "audit"
 *   (e.g. slow SLM fallback that outlasts the AuditPage polling window),
 *   refetchInterval fires every 3 s until status becomes "complete" or
 *   "error". This auto-populates empty tabs without a manual refresh.
 */

import React, { useCallback } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useSessionStore } from "../store/sessionStore";

import TopBar from "../components/layout/TopBar";
import TabBar from "../components/layout/TabBar";
import DataHealthPanel from "../components/dashboard/DataHealthPanel";
import NarrativePanel from "../components/dashboard/NarrativePanel";
import PlotlyChart from "../components/dashboard/PlotlyChart";
import CustomVizPanel from "../components/dashboard/CustomVizPanel";
import ChatPanel from "../components/dashboard/ChatPanel";
import FeReportTab from "../components/dashboard/FeReportTab";
import AuditLogTab from "../components/dashboard/AuditLogTab";
import DownloadsTab from "../components/dashboard/DownloadsTab";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorBanner from "../components/shared/ErrorBanner";
import type { ChartSpec } from "../types/chart";
import { getSession } from "../api/sessions";

// ---------------------------------------------------------------------------
// Tab definitions (outside component -- stable reference)
// ---------------------------------------------------------------------------

const TABS: import("../components/layout/TabBar").TabItem[] = [
  "Overview", "EDA Charts", "Custom Viz", "Chat",
  "Feature Engineering", "Audit Log", "Downloads",
].map((label) => ({ label }));

// Statuses that mean the pipeline is still running -- poll until it clears.
const PENDING_STATUSES = new Set(["processing", "audit", "upload"]);

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage(): React.ReactElement {
  const { sessionId } = useParams<{ sessionId: string }>();

  const dashboardTabBySession = useSessionStore((s) => s.dashboardTabBySession);
  const setDashboardTab       = useSessionStore((s) => s.setDashboardTab);
  const activeTab = dashboardTabBySession[sessionId ?? ""] ?? 0;
  const setActiveTab = useCallback(
    (tab: number) => { if (sessionId) setDashboardTab(sessionId, tab); },
    [sessionId, setDashboardTab],
  );

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: Boolean(sessionId),
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,

    // Poll every 3 s while the pipeline is still running.
    // Stops automatically once status becomes "complete" or "error".
    // This handles the slow-SLM-fallback case where DashboardPage is reached
    // before Phase 2/3 has finished, giving the user live tab population
    // without a manual reload.
    refetchInterval: (query) => {
      const status = (query.state.data as { session: { status: string } } | undefined)
        ?.session?.status;
      return status !== undefined && PENDING_STATUSES.has(status) ? 3_000 : false;
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <ErrorBanner message={isError ? (error as Error).message : "Session not found."} />
      </div>
    );
  }

  const { session, charts, eda_narrative, audit_log } = data;
  const feEntries = audit_log.filter((e) => e.agent_name === "engineer");
  const isPipelineRunning = PENDING_STATUSES.has(session.status);
  const pipelineFailed    = session.status === "error";

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          title={session.original_filename ?? "Dashboard"}
          status={session.status}
          llmProvider={session.llm_provider}
        />
        <TabBar tabs={TABS} activeIndex={activeTab} onTabChange={setActiveTab} />

        <main className="flex-1 overflow-y-auto p-6">

          {/* Pipeline still running -- auto-dismissed when status = complete */}
          {isPipelineRunning && (
            <div
              aria-live="polite"
              className="mb-4 flex items-center gap-2 rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] px-4 py-3 text-sm text-[var(--sage-accent)]"
            >
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[var(--sage-accent)] border-t-transparent" />
              Analysis pipeline running... tabs will populate automatically when complete.
            </div>
          )}

          {/* Phase 2/3 error banner (forwarded from AuditPage) */}
          {pipelineFailed && (
            <div className="mb-4">
              <ErrorBanner
                message={
                  session.error_message ??
                  "The analysis pipeline encountered an error. Some tabs may be incomplete."
                }
                variant="error"
              />
            </div>
          )}

          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              {activeTab === 0 && (
                <div className="space-y-6">
                  {eda_narrative && <NarrativePanel narrative={eda_narrative} />}
                  <DataHealthPanel session={session} narrative={eda_narrative} />
                </div>
              )}
              {activeTab === 1 && (
                <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                  {charts.length > 0 ? (
                    charts.map((chart: ChartSpec) => (
                      <PlotlyChart key={chart.id} chart={chart} />
                    ))
                  ) : (
                    <p className="col-span-2 py-12 text-center text-sm text-[var(--sage-text-muted)]">
                      {isPipelineRunning
                        ? "Charts will appear once the EDA pipeline completes."
                        : "No charts were generated for this session."}
                    </p>
                  )}
                </div>
              )}
              {activeTab === 2 && <CustomVizPanel sessionId={session.id} />}
              {activeTab === 3 && <ChatPanel sessionId={session.id} />}
              {activeTab === 4 && <FeReportTab feEntries={feEntries} narrative={eda_narrative} />}
              {activeTab === 5 && <AuditLogTab logs={audit_log} />}
              {activeTab === 6 && <DownloadsTab session={session} auditLog={audit_log} />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
  );
}
