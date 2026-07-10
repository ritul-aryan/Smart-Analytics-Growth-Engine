/**
 * frontend/src/components/shared/LoadingSpinner.tsx
 *
 * Consistent full-page and inline loading state component.
 *
 * Usage:
 *   <LoadingSpinner />                    — centred full-page spinner
 *   <LoadingSpinner size="sm" />          — small inline spinner
 *   <LoadingSpinner message="Analysing…" /> — spinner with label
 *   <LoadingSpinner inline />             — inline (no min-h-screen wrapper)
 */

import React from "react";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LoadingSpinnerProps {
  /** Size variant. Default: "md". */
  size?: "sm" | "md" | "lg";
  /** Optional label rendered below the spinner. */
  message?: string;
  /**
   * When true, renders without the full-page centering wrapper.
   * Use inside panels or cards where the parent controls layout.
   */
  inline?: boolean;
}

// ---------------------------------------------------------------------------
// Size map
// ---------------------------------------------------------------------------

const SIZE_CLASSES: Record<NonNullable<LoadingSpinnerProps["size"]>, string> = {
  sm: "h-4 w-4 border-2",
  md: "h-8 w-8 border-2",
  lg: "h-12 w-12 border-[3px]",
};

const TEXT_CLASSES: Record<NonNullable<LoadingSpinnerProps["size"]>, string> = {
  sm: "text-xs",
  md: "text-sm",
  lg: "text-base",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function LoadingSpinner({
  size = "md",
  message,
  inline = false,
}: LoadingSpinnerProps): React.ReactElement {
  const spinner = (
    <div
      role="status"
      aria-label={message ?? "Loading"}
      className="flex flex-col items-center gap-3"
    >
      <div
        className={[
          "animate-spin rounded-full",
          "border-[var(--sage-border-strong)] border-t-[var(--sage-accent)]",
          SIZE_CLASSES[size],
        ].join(" ")}
      />
      {message && (
        <p className={["text-[var(--sage-text-muted)]", TEXT_CLASSES[size]].join(" ")}>
          {message}
        </p>
      )}
    </div>
  );

  if (inline) {
    return spinner;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--sage-bg-base)]">
      {spinner}
    </main>
  );
}
