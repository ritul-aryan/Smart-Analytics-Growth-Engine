/**
 * frontend/src/components/audit/AnomalyCard.tsx
 *
 * Single anomaly review card with HITL action selector.
 *
 * DANGER WARNING RULE (Section 6.3 / Bug 2):
 * If null_rate > 0.40 AND the user selects "drop_rows" on a MISSING_DATA
 * anomaly, display a red banner showing how many rows will be deleted.
 */

import { useCallback } from "react";
import type { Anomaly, AnomalyType, UserDecision } from "../../types/session";

// Mirror of MISSING_DATA_DANGER_NULL_RATE in ai_engine/config.py
const DANGER_NULL_RATE = 0.40;

// ---------------------------------------------------------------------------
// Action definitions per anomaly type
// ---------------------------------------------------------------------------

const ACTIONS: Record<AnomalyType, Array<{ value: string; label: string }>> = {
  MISSING_DATA: [
    { value: "keep_as_is",   label: "Keep as-is" },
    { value: "drop_rows",    label: "Drop rows" },
    { value: "drop_column",  label: "Drop entire column" },
    { value: "fill_mean",    label: "Fill with mean" },
    { value: "fill_median",  label: "Fill with median" },
    { value: "fill_mode",    label: "Fill with mode" },
  ],
  STATISTICAL_OUTLIER: [
    { value: "keep_all",         label: "Keep all" },
    { value: "drop_rows",        label: "Drop outlier rows" },
    { value: "cap_iqr",          label: "Cap to IQR bounds" },
    { value: "fill_mean",        label: "Replace with inlier mean" },
    { value: "treat_as_missing", label: "Treat as missing" },
  ],
  LOGICAL_VIOLATION: [
    { value: "keep_as_is",       label: "Keep as-is" },
    { value: "drop_rows",        label: "Drop rows" },
    { value: "clamp_bounds",     label: "Clamp to bounds" },
    { value: "treat_as_missing", label: "Treat as missing" },
  ],
  ZERO_AS_MISSING: [
    { value: "keep_as_is", label: "Keep as-is" },
    { value: "fill_mean",  label: "Impute with safe mean" },
    { value: "drop_rows",  label: "Drop rows" },
  ],
  DUPLICATE_ROWS: [
    { value: "keep_all",           label: "Keep all" },
    { value: "remove_duplicates",  label: "Remove duplicates (keep first)" },
  ],
  HIGH_NULL_DENSITY_ROWS: [
    { value: "keep_all",  label: "Keep all" },
    { value: "drop_rows", label: "Drop sparse rows" },
    { value: "fill_mean", label: "Fill numeric nulls with mean" },
  ],
  PII_DETECTED: [
    { value: "keep_as_is",  label: "Keep as-is" },
    { value: "redact",      label: "Redact ([REDACTED])" },
    { value: "hash_sha256", label: "Hash (SHA-256)" },
    { value: "drop_column", label: "Drop column" },
  ],
};

// Severity → prototype SEV tokens. The app uses three tiers; its most
// severe tier ("high") maps to --sage-crit so the red danger signal from
// the SAGE.html prototype is preserved.
const SEVERITY_CHIP: Record<string, string> = {
  high:   "border-[var(--sage-crit)] bg-[var(--sage-crit-soft)] text-[var(--sage-crit)]",
  medium: "border-[var(--sage-high)] bg-[var(--sage-high-soft)] text-[var(--sage-high)]",
  low:    "border-[var(--sage-low)] bg-[var(--sage-low-soft)] text-[var(--sage-low)]",
};

const SEVERITY_BORDER: Record<string, string> = {
  high:   "border-[var(--sage-crit)]",
  medium: "border-[var(--sage-high)]",
  low:    "border-[var(--sage-low)]",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AnomalyCardProps {
  anomaly: Anomaly;
  decision: UserDecision | undefined;
  onDecisionChange: (decision: UserDecision) => void;
  totalRows: number | null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AnomalyCard({
  anomaly,
  decision,
  onDecisionChange,
  totalRows,
}: AnomalyCardProps): React.ReactElement {
  const actions = ACTIONS[anomaly.anomaly_type] ?? [];
  const selectedAction = decision?.action ?? "";

  // Prefer the true per-column count (details.total_flagged) so the number shown
  // matches what the janitor will actually change. Fall back to affected_rows for
  // older sessions whose anomaly records predate this field.
  const trueCount =
    (anomaly.details?.total_flagged as number | undefined) ?? anomaly.affected_rows;

  const handleActionChange = useCallback(
    (action: string) => {
      // Auto-populate params for clamp_bounds from anomaly details
      let params: Record<string, unknown> | undefined;
      if (action === "clamp_bounds") {
        params = {
          min_bound: anomaly.details.min_bound,
          max_bound: anomaly.details.max_bound,
        };
      }
      onDecisionChange({ anomaly_id: anomaly.id, action, params });
    },
    [anomaly, onDecisionChange],
  );

  // Editable clamp_bounds min/max — lets the user override the LLM-suggested
  // bounds (e.g. change [0, 120] to [0, 100]) instead of only ever sending
  // the auto-populated anomaly.details values back to the backend.
  const handleBoundChange = useCallback(
    (bound: "min_bound" | "max_bound", raw: string) => {
      const parsed = Number(raw);
      const value =
        raw.trim() === "" || Number.isNaN(parsed)
          ? anomaly.details[bound]
          : parsed;

      const currentParams = decision?.params as
        | { min_bound?: number; max_bound?: number }
        | undefined;

      const params = {
        min_bound:
          bound === "min_bound"
            ? value
            : currentParams?.min_bound ?? anomaly.details.min_bound,
        max_bound:
          bound === "max_bound"
            ? value
            : currentParams?.max_bound ?? anomaly.details.max_bound,
      };

      onDecisionChange({ anomaly_id: anomaly.id, action: "clamp_bounds", params });
    },
    [anomaly, decision, onDecisionChange],
  );

  // Danger warning: drop_rows on MISSING_DATA with high null_rate
  const showDangerWarning =
    anomaly.anomaly_type === "MISSING_DATA" &&
    selectedAction === "drop_rows" &&
    (anomaly.null_rate ?? 0) > DANGER_NULL_RATE;

  const rowsAtRisk = trueCount;
  const pct = totalRows ? ((rowsAtRisk / totalRows) * 100).toFixed(1) : null;

  const cardBorder = SEVERITY_BORDER[anomaly.severity] ?? SEVERITY_BORDER["low"];
  const chipClass  = SEVERITY_CHIP[anomaly.severity] ?? SEVERITY_CHIP["low"];

  return (
    <article className={`rounded-xl border bg-[var(--sage-bg-elevated)] p-5 shadow-sm ${cardBorder}`}>
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-[var(--sage-text-primary)]">
            {anomaly.anomaly_type.replace(/_/g, " ")}
          </h3>
          {anomaly.column_name && (
            <p className="text-xs text-[var(--sage-text-muted)]">
              Column: <code className="font-mono">{anomaly.column_name}</code>
            </p>
          )}
        </div>
        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${chipClass}`}>
          {anomaly.severity}
        </span>
      </div>

      {/* Stats row */}
      <div className="mt-2 flex flex-wrap gap-4 text-sm text-[var(--sage-text-muted)]">
        <span>{trueCount.toLocaleString()} rows affected</span>
        {anomaly.null_rate !== null && (
          <span>Null rate: {(anomaly.null_rate * 100).toFixed(1)}%</span>
        )}
        {anomaly.details.lower_fence !== undefined && (
          <span>
            Fences: [{anomaly.details.lower_fence?.toFixed(2)}, {anomaly.details.upper_fence?.toFixed(2)}]
          </span>
        )}
        {anomaly.details.min_bound !== undefined && (
          <span>
            Bounds: [{anomaly.details.min_bound}, {anomaly.details.max_bound}]
          </span>
        )}
        {anomaly.details.pii_types_found && (
          <span>PII types: {anomaly.details.pii_types_found.join(", ")}</span>
        )}
      </div>

      {/* Danger warning — Bug 2 */}
      {showDangerWarning && (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-[var(--sage-crit)] bg-[var(--sage-crit-soft)] px-4 py-3 text-sm font-medium text-[var(--sage-crit)]"
        >
          ⚠ Dropping rows will delete{" "}
          <strong>{rowsAtRisk.toLocaleString()} rows</strong>
          {pct && ` (${pct}% of the dataset)`}. This column has a very high
          null rate ({((anomaly.null_rate ?? 0) * 100).toFixed(1)}%) — consider
          filling or dropping the column instead.
        </div>
      )}

      {/* Action selector */}
      <div className="mt-4">
        <label className="mb-1 block text-xs font-medium text-[var(--sage-text-muted)]">
          Action
        </label>
        <select
          value={selectedAction}
          onChange={(e) => handleActionChange(e.target.value)}
          className="w-full rounded-lg border border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] px-3 py-2 text-sm text-[var(--sage-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--sage-accent)]"
          aria-label={`Action for ${anomaly.anomaly_type} on ${anomaly.column_name ?? "row-level"}`}
        >
          <option value="" disabled>
            — choose an action —
          </option>
          {actions.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </div>

      {/* Editable clamp bounds — only for the selected clamp_bounds action */}
      {selectedAction === "clamp_bounds" && (
        <div className="mt-3 flex flex-wrap gap-3">
          <div className="flex-1 min-w-[8rem]">
            <label className="mb-1 block text-xs font-medium text-[var(--sage-text-muted)]">
              Min bound
            </label>
            <input
              type="number"
              value={
                (decision?.params as { min_bound?: number } | undefined)?.min_bound ??
                anomaly.details.min_bound ??
                ""
              }
              onChange={(e) => handleBoundChange("min_bound", e.target.value)}
              className="w-full rounded-lg border border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] px-3 py-2 text-sm text-[var(--sage-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--sage-accent)]"
              aria-label="Min bound"
            />
          </div>
          <div className="flex-1 min-w-[8rem]">
            <label className="mb-1 block text-xs font-medium text-[var(--sage-text-muted)]">
              Max bound
            </label>
            <input
              type="number"
              value={
                (decision?.params as { max_bound?: number } | undefined)?.max_bound ??
                anomaly.details.max_bound ??
                ""
              }
              onChange={(e) => handleBoundChange("max_bound", e.target.value)}
              className="w-full rounded-lg border border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] px-3 py-2 text-sm text-[var(--sage-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--sage-accent)]"
              aria-label="Max bound"
            />
          </div>
        </div>
      )}
    </article>
  );
}
