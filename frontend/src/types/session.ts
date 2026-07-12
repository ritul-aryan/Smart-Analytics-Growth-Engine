/**
 * frontend/src/types/session.ts
 *
 * Shared TypeScript types for Session, Anomaly, and AuditLog entities.
 * All types mirror the backend SQLAlchemy models exactly — any schema
 * change in backend/db/models.py must be reflected here.
 */

// ---------------------------------------------------------------------------
// Enumerations
// ---------------------------------------------------------------------------

export type SessionStatus =
  | "upload"
  | "audit"
  | "processing"
  | "complete"
  | "error";

export type AnomalyType =
  | "DUPLICATE_ROWS"
  | "MISSING_DATA"
  | "ZERO_AS_MISSING"
  | "LOGICAL_VIOLATION"
  | "STATISTICAL_OUTLIER"
  | "HIGH_NULL_DENSITY_ROWS"
  | "PII_DETECTED";

export type Severity = "low" | "medium" | "high";

export type LLMProvider =
  | "gemini-2.0-flash"
  | "gemini-1.5-flash"
  | "ollama";

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export interface Session {
  id: string;
  created_at: string;           // ISO 8601
  updated_at: string;
  status: SessionStatus;
  original_filename: string;
  stored_filename: string;
  user_intent: string | null;
  llm_provider: LLMProvider | null;
  row_count: number | null;
  col_count: number | null;
  quality_score_before: number | null;  // 0–100
  quality_score_after: number | null;
  column_renames: Record<string, string> | null;
  metadata_summary: string | null;
  error_message: string | null;
}

// ---------------------------------------------------------------------------
// Anomaly
// ---------------------------------------------------------------------------

/**
 * Details payload varies by anomaly_type.
 * Use discriminated union helpers (see getAnomalyDetails) for type-safe access.
 */
export interface AnomalyDetails {
  // DUPLICATE_ROWS
  sample_indices?: number[];
  // All anomaly types (true per-column count, before priority-chain de-duplication)
  total_flagged?: number;
  // MISSING_DATA
  null_rate?: number;
  // ZERO_AS_MISSING
  zero_count?: number;
  // LOGICAL_VIOLATION
  min_bound?: number;
  max_bound?: number;
  description?: string;
  // STATISTICAL_OUTLIER
  lower_fence?: number;
  upper_fence?: number;
  // HIGH_NULL_DENSITY_ROWS
  threshold?: number;
  mean_null_density?: number;
  // PII_DETECTED
  pii_types_found?: string[];
}

export interface Anomaly {
  id: string;
  session_id: string;
  anomaly_type: AnomalyType;
  column_name: string | null;
  affected_rows: number;
  null_rate: number | null;
  severity: Severity;
  details: AnomalyDetails;
  user_action: string | null;
  action_params: Record<string, unknown> | null;
  resolved_at: string | null;
  display_order: number;
}

// ---------------------------------------------------------------------------
// AuditLog
// ---------------------------------------------------------------------------

export interface AuditLog {
  id: string;
  session_id: string;
  agent_name: string;
  phase: string;
  action: string;
  reason: string;
  column_affected: string | null;
  rows_affected: number;
  before_value: Record<string, unknown> | null;
  after_value: Record<string, unknown> | null;
  is_llm_decision: boolean;
  llm_prompt_summary: string | null;
  timestamp: string;  // ISO 8601
}

// ---------------------------------------------------------------------------
// User decision (HITL — sent to POST /api/analyze/complete)
// ---------------------------------------------------------------------------

export interface UserDecision {
  anomaly_id: string;
  action: string;
  params?: Record<string, unknown>;
}
