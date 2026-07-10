/**
 * frontend/src/components/upload/IntentInput.tsx
 *
 * Plain-English intent text field.
 *
 * The user describes what they want to learn from the data.
 * This string is passed to every LLM call as context throughout the pipeline.
 * Providing a clear intent improves header normalisation, domain profiling,
 * and chart selection quality — so the component nudges users toward detail.
 */

import { useCallback } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface IntentInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const MAX_LENGTH = 500;

const PLACEHOLDERS = [
  "e.g. Analyse customer churn — identify which users are at risk and why",
  "e.g. Understand sales trends across regions and product categories",
  "e.g. Find data quality issues in our inventory export before importing to CRM",
  "e.g. Explore correlations between employee satisfaction and team performance",
];

// Use a stable index derived from the day so it varies but doesn't flicker
const PLACEHOLDER = PLACEHOLDERS[new Date().getDate() % PLACEHOLDERS.length] ?? PLACEHOLDERS[0];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function IntentInput({
  value,
  onChange,
  disabled = false,
}: IntentInputProps): React.ReactElement {
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value.slice(0, MAX_LENGTH));
    },
    [onChange],
  );

  const remaining = MAX_LENGTH - value.length;
  const isNearLimit = remaining < 50;

  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor="user-intent"
        className="text-sm font-medium text-[var(--sage-text-muted)]"
      >
        What do you want to learn from this data?{" "}
        <span className="font-normal text-[var(--sage-text-dim)]">(optional but recommended)</span>
      </label>

      <textarea
        id="user-intent"
        value={value}
        onChange={handleChange}
        disabled={disabled}
        rows={3}
        maxLength={MAX_LENGTH}
        placeholder={PLACEHOLDER}
        className={`w-full rounded-lg border px-3 py-2 text-sm text-[var(--sage-text-primary)] placeholder:text-[var(--sage-text-dim)] resize-none transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--sage-accent)] ${
          disabled
            ? "border-[var(--sage-border)] bg-[var(--sage-bg-overlay)] text-[var(--sage-text-dim)] cursor-not-allowed"
            : "border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] hover:border-[var(--sage-accent-border)]"
        }`}
        aria-describedby="intent-hint intent-counter"
      />

      <div className="flex items-start justify-between gap-4">
        <p id="intent-hint" className="text-xs text-[var(--sage-text-dim)]">
          A clear intent improves header normalisation, domain profiling, and
          chart selection throughout the pipeline.
        </p>
        <p
          id="intent-counter"
          className={`shrink-0 text-xs tabular-nums ${
            isNearLimit ? "text-[var(--sage-high)]" : "text-[var(--sage-text-dim)]"
          }`}
          aria-live="polite"
        >
          {remaining}/{MAX_LENGTH}
        </p>
      </div>
    </div>
  );
}
