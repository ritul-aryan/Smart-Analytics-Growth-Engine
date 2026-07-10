/**
 * frontend/src/store/sessionStore.ts
 *
 * Zustand store — current active session state.
 *
 * Holds the session detail for whichever session is currently open in the
 * UI, plus the list of user HITL decisions being built before submission.
 * Server data is owned by TanStack Query — this store only tracks UI state
 * that needs to persist across navigations without refetching:
 *   - activeSessionId        (which session is open)
 *   - pendingDecisions       (HITL actions chosen but not yet submitted)
 *   - pollingActive          (whether Phase 1 polling loop is running)
 *   - dashboardTabBySession  (last active tab per session — survives navigation)
 */

import { create } from "zustand";
import type { UserDecision } from "../types/session";

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface SessionState {
  /** UUID of the session currently open in the UI, or null if none. */
  activeSessionId: string | null;

  /**
   * HITL decisions accumulated on the AuditPage.
   * Keyed by anomaly_id for O(1) upsert — converted to array on submit.
   */
  pendingDecisions: Record<string, UserDecision>;

  /** True while Phase 1 background polling is running. */
  pollingActive: boolean;

  /**
   * Last-active dashboard tab index per session (keyed by sessionId).
   * Persists across navigations so returning to a session restores the
   * tab the user was on rather than snapping back to Overview (tab 0).
   */
  dashboardTabBySession: Record<string, number>;

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  /** Open a session in the UI. Clears any stale pending decisions. */
  setActiveSession: (sessionId: string) => void;

  /** Clear the active session (e.g., on upload of a new file). */
  clearActiveSession: () => void;

  /** Persist the active dashboard tab index for a specific session. */
  setDashboardTab: (sessionId: string, tab: number) => void;

  /**
   * Set or update the user's decision for one anomaly.
   * Calling with the same anomaly_id replaces the previous choice.
   */
  setDecision: (decision: UserDecision) => void;

  /** Remove a single decision (user cleared their choice). */
  removeDecision: (anomalyId: string) => void;

  /** Clear all pending decisions (after successful submit). */
  clearDecisions: () => void;

  /** Returns pending decisions as an ordered array. */
  getDecisionsArray: () => UserDecision[];

  setPollingActive: (active: boolean) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useSessionStore = create<SessionState>((set, get) => ({
  activeSessionId: null,
  pendingDecisions: {},
  pollingActive: false,
  dashboardTabBySession: {},

  setActiveSession: (sessionId) =>
    set({ activeSessionId: sessionId, pendingDecisions: {} }),

  clearActiveSession: () =>
    set({ activeSessionId: null, pendingDecisions: {}, pollingActive: false }),

  setDashboardTab: (sessionId, tab) =>
    set((state) => ({
      dashboardTabBySession: { ...state.dashboardTabBySession, [sessionId]: tab },
    })),

  setDecision: (decision) =>
    set((state) => ({
      pendingDecisions: {
        ...state.pendingDecisions,
        [decision.anomaly_id]: decision,
      },
    })),

  removeDecision: (anomalyId) =>
    set((state) => {
      const next = { ...state.pendingDecisions };
      delete next[anomalyId];
      return { pendingDecisions: next };
    }),

  clearDecisions: () => set({ pendingDecisions: {} }),

  getDecisionsArray: () => Object.values(get().pendingDecisions),

  setPollingActive: (active) => set({ pollingActive: active }),
}));
