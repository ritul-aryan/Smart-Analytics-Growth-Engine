/**
 * frontend/src/components/shared/ThemeToggle.tsx
 *
 * Light / Dark mode toggle button.
 *
 * Reads and writes theme via uiStore only. App.tsx is the single owner
 * of the "dark" / "light" classes on <html>; this component must never
 * touch the DOM directly.  Persists via uiStore's localStorage
 * middleware — survives page refresh.
 *
 * Usage:
 *   <ThemeToggle />           — icon-only button (default)
 *   <ThemeToggle showLabel /> — icon + "Light" / "Dark" label
 */

import React from "react";
import { useUiStore } from "../../store/uiStore";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ThemeToggleProps {
  /** Render a text label next to the icon. Default: false. */
  showLabel?: boolean;
  /** Extra Tailwind classes for the button. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function SunIcon(): React.ReactElement {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon(): React.ReactElement {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ThemeToggle({
  showLabel = false,
  className = "",
}: ThemeToggleProps): React.ReactElement {
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className={[
        "flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm transition-colors",
        "text-[var(--sage-text-muted)] hover:bg-[var(--sage-bg-overlay)] hover:text-[var(--sage-text-primary)]",
        className,
      ].join(" ")}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
      {showLabel && (
        <span className="select-none">{isDark ? "Light" : "Dark"}</span>
      )}
    </button>
  );
}
