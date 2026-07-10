/**
 * frontend/src/components/dashboard/BeforeAfterToggle.tsx
 *
 * Toggle switch for switching between raw (before cleaning) and clean
 * (after cleaning) views on any chart in the EDA portfolio.
 *
 * Stateless — the parent owns the active state and passes the two chart
 * specs.  When only one spec is provided the toggle is disabled.
 *
 * Usage:
 *   const [showClean, setShowClean] = useState(true);
 *
 *   <BeforeAfterToggle
 *     showClean={showClean}
 *     onToggle={setShowClean}
 *     hasClean={!!cleanChart}
 *   />
 */

import React from "react";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BeforeAfterToggleProps {
  /** True → showing the post-cleaning chart.  False → raw chart. */
  showClean: boolean;
  /** Called when the user clicks the toggle. */
  onToggle: (showClean: boolean) => void;
  /**
   * Whether a clean version exists.  When false the toggle is rendered
   * but disabled and the "After" option is greyed out.
   */
  hasClean?: boolean;
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BeforeAfterToggle({
  showClean,
  onToggle,
  hasClean = true,
  className = "",
}: BeforeAfterToggleProps): React.ReactElement {
  return (
    <div
      className={[
        "inline-flex items-center rounded-lg border p-0.5",
        "border-[var(--sage-border)] bg-[var(--sage-bg-overlay)]",
        className,
      ].join(" ")}
      role="group"
      aria-label="Data version toggle"
    >
      {/* Before (raw) */}
      <button
        type="button"
        onClick={() => onToggle(false)}
        aria-pressed={!showClean}
        className={[
          "rounded-md px-3 py-1 text-xs font-medium transition-colors",
          !showClean
            ? "bg-[var(--sage-bg-elevated)] text-[var(--sage-text-primary)] shadow-sm"
            : "text-[var(--sage-text-muted)] hover:text-[var(--sage-text-primary)]",
        ].join(" ")}
      >
        Before
      </button>

      {/* After (clean) */}
      <button
        type="button"
        onClick={() => hasClean && onToggle(true)}
        aria-pressed={showClean}
        disabled={!hasClean}
        className={[
          "rounded-md px-3 py-1 text-xs font-medium transition-colors",
          showClean && hasClean
            ? "bg-[var(--sage-bg-elevated)] text-[var(--sage-text-primary)] shadow-sm"
            : hasClean
              ? "text-[var(--sage-text-muted)] hover:text-[var(--sage-text-primary)]"
              : "cursor-not-allowed text-[var(--sage-text-dim)]",
        ].join(" ")}
      >
        After
      </button>
    </div>
  );
}
