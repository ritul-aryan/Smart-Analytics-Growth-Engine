/**
 * frontend/src/store/uiStore.ts
 *
 * Zustand store for global UI preferences.
 *
 * Persists theme, active LLM provider, API keys, and analysis settings to
 * localStorage so users do not have to re-configure on every page load.
 *
 * ActiveProvider is the user-facing concept (gemini / claude / ollama).
 * llmProvider is the backend-compatible string sent with analyze/start.
 * When activeProvider is set, llmProvider is kept in sync for the
 * providers the backend currently supports.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LLMProvider } from "../types/session";

// ---------------------------------------------------------------------------
// Provider types
// ---------------------------------------------------------------------------

/** Simplified provider identifier used in Settings UI and sidebar. */
export type ActiveProvider = "gemini" | "claude" | "ollama";

/** API keys keyed by provider. Ollama never needs one. */
export interface ApiKeys {
  gemini: string;
  claude: string;
  ollama: string;
}

/** Map ActiveProvider to the backend llm_provider value. */
export const ACTIVE_PROVIDER_TO_LLM: Record<ActiveProvider, LLMProvider> = {
  gemini: "gemini-2.0-flash",
  claude: "gemini-2.0-flash",   // Claude backend support pending; falls back to Gemini
  ollama: "ollama",
};

// ---------------------------------------------------------------------------
// Analysis settings (Section 8.3)
// ---------------------------------------------------------------------------

export interface AnalysisSettings {
  /** Which categorical columns get OHE'd. Range: 2-50. Default: 10. */
  oheMaxUnique: number;
  /** Skewness threshold for log transform. Range: 0.5-5.0. Default: 1.5. */
  logSkewThreshold: number;
  /** Minimum |r| for interaction term. Range: 0.1-0.99. Default: 0.50. */
  correlationThreshold: number;
  /** IQR multiplier for outlier detection. Range: 1.5-5.0. Default: 3.0. */
  outlierIqrMultiplier: number;
  /** Row null fraction threshold for HIGH_NULL_DENSITY_ROWS. Range: 0.1-0.9. Default: 0.50. */
  nullDensityThreshold: number;
}

export const DEFAULT_ANALYSIS_SETTINGS: AnalysisSettings = {
  oheMaxUnique:          10,
  logSkewThreshold:      1.5,
  correlationThreshold:  0.50,
  outlierIqrMultiplier:  3.0,
  nullDensityThreshold:  0.50,
};

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

type Theme = "light" | "dark";

interface UiState {
  theme: Theme;

  /**
   * User-facing provider selection (gemini / claude / ollama).
   * Persisted. Controls the sidebar indicator and Settings page.
   */
  activeProvider: ActiveProvider;

  /**
   * Backend-compatible provider string derived from activeProvider.
   * Sent as llm_provider in analyze/start requests.
   * Persisted for backward compatibility with existing sessions.
   */
  llmProvider: LLMProvider;

  /**
   * API keys stored in localStorage. Never sent to the backend directly;
   * the frontend injects the key into request headers or form fields
   * when the relevant provider is active.
   * Note: localStorage is not encrypted; advise users on shared machines.
   */
  apiKeys: ApiKeys;

  /** Whether the left sidebar is collapsed. Not persisted. */
  sidebarCollapsed: boolean;

  /** User-configurable analysis settings. Persisted. */
  analysisSettings: AnalysisSettings;

  // Actions
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  /** Set the active provider and sync llmProvider for the backend. */
  setActiveProvider: (provider: ActiveProvider) => void;
  /** Legacy: kept for backward compatibility with existing upload flow. */
  setLlmProvider: (provider: LLMProvider) => void;
  /** Update a single API key. */
  setApiKey: (provider: ActiveProvider, key: string) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setAnalysisSettings: (settings: Partial<AnalysisSettings>) => void;
  resetAnalysisSettings: () => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: "dark",
      activeProvider: "gemini",
      llmProvider: "gemini-2.0-flash",
      apiKeys: { gemini: "", claude: "", ollama: "" },
      sidebarCollapsed: false,
      analysisSettings: DEFAULT_ANALYSIS_SETTINGS,

      toggleTheme: () =>
        set((state) => ({ theme: state.theme === "light" ? "dark" : "light" })),

      setTheme: (theme) => set({ theme }),

      setActiveProvider: (provider) =>
        set({
          activeProvider: provider,
          llmProvider: ACTIVE_PROVIDER_TO_LLM[provider],
        }),

      setLlmProvider: (provider) => set({ llmProvider: provider }),

      setApiKey: (provider, key) =>
        set((state) => ({
          apiKeys: { ...state.apiKeys, [provider]: key },
        })),

      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setAnalysisSettings: (patch) =>
        set((state) => ({
          analysisSettings: { ...state.analysisSettings, ...patch },
        })),

      resetAnalysisSettings: () =>
        set({ analysisSettings: DEFAULT_ANALYSIS_SETTINGS }),
    }),
    {
      name: "mae-ui-preferences",
      // sidebarCollapsed intentionally excluded (resets on reload)
      partialize: (state) => ({
        theme:             state.theme,
        activeProvider:    state.activeProvider,
        llmProvider:       state.llmProvider,
        apiKeys:           state.apiKeys,
        analysisSettings:  state.analysisSettings,
      }),
    },
  ),
);
