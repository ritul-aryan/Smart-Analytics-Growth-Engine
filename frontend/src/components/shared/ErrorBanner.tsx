/**
 * frontend/src/components/shared/ErrorBanner.tsx
 *
 * Consistent error display component.
 *
 * Usage:
 *   <ErrorBanner message="Something went wrong." />
 *   <ErrorBanner message={err} onRetry={() => refetch()} />
 *   <ErrorBanner message={err} onDismiss={() => setError(null)} />
 *   <ErrorBanner message={err} variant="warning" />
 */

import React from "react";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ErrorBannerProps {
  /** Error message string or Error object to display. */
  message: string | Error | unknown;
  /** Visual style. Default: "error". */
  variant?: "error" | "warning" | "info";
  /** Optional retry callback — renders a "Try again" button. */
  onRetry?: () => void;
  /** Optional dismiss callback — renders an × button. */
  onDismiss?: () => void;
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Variant config
// ---------------------------------------------------------------------------

// Variants map to the prototype severity tokens: error → crit,
// warning → high, info → low. Soft fills adapt to both themes.
const VARIANT_STYLES = {
  error: {
    container: "bg-[var(--sage-crit-soft)] border-[var(--sage-crit)] text-[var(--sage-crit)]",
    icon: "text-[var(--sage-crit)]",
    button: "text-[var(--sage-crit)] hover:opacity-80",
  },
  warning: {
    container: "bg-[var(--sage-high-soft)] border-[var(--sage-high)] text-[var(--sage-high)]",
    icon: "text-[var(--sage-high)]",
    button: "text-[var(--sage-high)] hover:opacity-80",
  },
  info: {
    container: "bg-[var(--sage-low-soft)] border-[var(--sage-low)] text-[var(--sage-low)]",
    icon: "text-[var(--sage-low)]",
    button: "text-[var(--sage-low)] hover:opacity-80",
  },
};

const ICONS = {
  error: (
    <svg className="h-5 w-5 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
    </svg>
  ),
  warning: (
    <svg className="h-5 w-5 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
    </svg>
  ),
  info: (
    <svg className="h-5 w-5 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clipRule="evenodd" />
    </svg>
  ),
};

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function extractMessage(message: string | Error | unknown): string {
  if (typeof message === "string") return message;
  if (message instanceof Error) return message.message;
  return "An unexpected error occurred.";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ErrorBanner({
  message,
  variant = "error",
  onRetry,
  onDismiss,
  className = "",
}: ErrorBannerProps): React.ReactElement {
  const styles = VARIANT_STYLES[variant];
  const text = extractMessage(message);

  return (
    <div
      role="alert"
      className={[
        "flex items-start gap-3 rounded-xl border px-4 py-3 text-sm",
        styles.container,
        className,
      ].join(" ")}
    >
      <span className={styles.icon}>{ICONS[variant]}</span>

      <p className="flex-1 leading-relaxed">{text}</p>

      <div className="flex shrink-0 items-center gap-2">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className={["font-medium underline underline-offset-2", styles.button].join(" ")}
          >
            Try again
          </button>
        )}
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className={["rounded p-0.5 transition-colors", styles.button].join(" ")}
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
