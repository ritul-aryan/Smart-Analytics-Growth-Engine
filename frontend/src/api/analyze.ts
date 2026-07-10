/**
 * frontend/src/api/analyze.ts
 *
 * Typed wrappers for the Phase 1 and Phase 2+3 analysis endpoints.
 *
 * startAnalysis   — POST /api/analyze/start   (multipart form upload)
 * completeAnalysis — POST /api/analyze/complete (JSON decisions payload)
 */

import { apiPost } from "./client";
import type {
  AnalyzeCompleteRequest,
  AnalyzeCompleteResponse,
  AnalyzeStartResponse,
} from "../types/api";
import type { UserDecision } from "../types/session";
import { useUiStore } from "../store/uiStore";
import type { AnalysisSettings } from "../store/uiStore";

// ---------------------------------------------------------------------------
// BYOK key injection
// ---------------------------------------------------------------------------

/**
 * HTTP header carrying the user-supplied (BYOK) LLM API key.
 * Mirrored in backend/config.py (LLM_API_KEY_HEADER) — keep in sync.
 */
const LLM_API_KEY_HEADER = "X-LLM-API-Key";

/**
 * Return the stored API key matching the backend provider string, or null.
 *
 * The key is matched to the provider FAMILY of the request, not to the
 * provider card selected in Settings. This matters while 'claude' still
 * maps to 'gemini-2.0-flash' (backend Claude support pending): sending an
 * Anthropic key on a Gemini request would poison the call, so the Gemini
 * key is used for gemini-* requests and apiKeys.claude will flow
 * automatically once the backend resolves a claude-* provider string.
 * Ollama is local and keyless.
 */
function apiKeyForProvider(llmProvider: string): string | null {
  const { apiKeys } = useUiStore.getState();
  if (llmProvider.startsWith("gemini")) return apiKeys.gemini.trim() || null;
  if (llmProvider.startsWith("claude")) return apiKeys.claude.trim() || null;
  return null;
}

// ---------------------------------------------------------------------------
// Phase 1 — start
// ---------------------------------------------------------------------------

/**
 * Upload a file and trigger Phase 1 anomaly detection.
 *
 * Uses multipart/form-data so the file bytes are sent as-is.
 * Returns immediately with a session_id — caller should poll
 * getSession() until status === "audit".
 */
export async function startAnalysis(
  file: File,
  userIntent: string,
  llmProvider: string,
  settings?: AnalysisSettings,
): Promise<AnalyzeStartResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("user_intent", userIntent);
  form.append("llm_provider", llmProvider);
  if (settings) {
    form.append("ohe_max_unique",         String(settings.oheMaxUnique));
    form.append("log_skew_threshold",     String(settings.logSkewThreshold));
    form.append("correlation_threshold",  String(settings.correlationThreshold));
    form.append("outlier_iqr_multiplier", String(settings.outlierIqrMultiplier));
    form.append("null_density_threshold", String(settings.nullDensityThreshold));
  }

  // BYOK: attach the user's stored key for this provider family, if any.
  // The backend uses it for this request only and never persists it.
  const apiKey = apiKeyForProvider(llmProvider);
  const headers = apiKey ? { [LLM_API_KEY_HEADER]: apiKey } : undefined;

  return apiPost<AnalyzeStartResponse>("/api/analyze/start", form, headers);
}

// ---------------------------------------------------------------------------
// Phase 2+3 -- complete
// ---------------------------------------------------------------------------

/**
 * Submit HITL decisions and trigger Phase 2 cleaning + Phase 3 EDA.
 *
 * Returns immediately with 202 -- poll getSession() until
 * status === "complete".
 */
export async function completeAnalysis(
  sessionId: string,
  decisions: UserDecision[],
): Promise<AnalyzeCompleteResponse> {
  const body: AnalyzeCompleteRequest = {
    session_id: sessionId,
    decisions,
  };
  return apiPost<AnalyzeCompleteResponse>("/api/analyze/complete", body);
}
