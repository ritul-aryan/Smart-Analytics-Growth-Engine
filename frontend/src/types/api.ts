/**
 * frontend/src/types/api.ts
 *
 * API request and response shapes.  Every type here corresponds 1-to-1
 * with a Pydantic response model in the backend.  Keep in sync with
 * backend/api/*.py whenever endpoint schemas change.
 */

import type { Anomaly, AuditLog, Session, UserDecision } from "./session";
import type { ChartSpec, EdaNarrative } from "./chart";

// ---------------------------------------------------------------------------
// Generic API envelope
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string;
  status: number;
}

// ---------------------------------------------------------------------------
// POST /api/analyze/start
// ---------------------------------------------------------------------------

export interface AnalyzeStartRequest {
  file: File;
  user_intent: string;
  llm_provider: string;
}

export interface AnalyzeStartResponse {
  session_id: string;
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// POST /api/analyze/complete
// ---------------------------------------------------------------------------

export interface AnalyzeCompleteRequest {
  session_id: string;
  decisions: UserDecision[];
}

// Mirrors backend AnalyzeCompleteResponse exactly: session_id, status, message
export interface AnalyzeCompleteResponse {
  session_id: string;
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// GET /api/session/{id}
// ---------------------------------------------------------------------------

export interface SessionDetailResponse {
  session: Session;
  anomalies: Anomaly[];
  audit_log: AuditLog[];
  charts: ChartSpec[];
  eda_narrative: EdaNarrative | null;
}

// ---------------------------------------------------------------------------
// GET /api/sessions
// ---------------------------------------------------------------------------

export interface SessionListResponse {
  sessions: Session[];
  total: number;
}

// ---------------------------------------------------------------------------
// POST /api/chat
// ---------------------------------------------------------------------------

export interface ChatRequest {
  session_id: string;
  message: string;
}

// Mirrors backend ChatMessageOut — backend sends `timestamp`, not `created_at`
export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  has_chart: boolean;
  chart_id: string | null;
}

export interface ChatResponse {
  message: ChatMessage;
  chart: ChartSpec | null;
}

// ---------------------------------------------------------------------------
// POST /api/upload  /  GET /api/download/{filename}
// ---------------------------------------------------------------------------

// Mirrors backend UploadResponse — backend returns file_id, not session_id
export interface UploadResponse {
  file_id: string;
  stored_filename: string;
  original_filename: string;
  size_bytes: number;
}

export interface DownloadUrlResponse {
  url: string;
  filename: string;
}
