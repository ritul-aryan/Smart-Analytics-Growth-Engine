/**
 * frontend/src/components/layout/TopBar.tsx
 *
 * Page header bar — adapts to the active theme via CSS variables.
 *
 * Shows: breadcrumb · filename · status pill · LLM chip · theme toggle
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import type { SessionStatus, LLMProvider } from "../../types/session";
import { useUiStore } from "../../store/uiStore";
import LLMProviderSelector from "../shared/LLMProviderSelector";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface TopBarProps {
  title: string;
  status?: SessionStatus;
  llmProvider?: LLMProvider | null;
  breadcrumb?: BreadcrumbItem[];
}

// ---------------------------------------------------------------------------
// Status pill
// ---------------------------------------------------------------------------

// Status pills mapped to prototype tokens (colour + matching -soft fill).
const STATUS_CONFIG: Record<SessionStatus, { label: string; color: string; bg: string }> = {
  upload:     { label: "Uploading",  color: "var(--sage-text-muted)", bg: "var(--sage-bg-overlay)" },
  audit:      { label: "Review",     color: "var(--sage-med)",        bg: "var(--sage-med-soft)" },
  processing: { label: "Processing", color: "var(--sage-low)",        bg: "var(--sage-low-soft)" },
  complete:   { label: "Complete",   color: "var(--sage-good)",       bg: "var(--sage-good-soft)" },
  error:      { label: "Error",      color: "var(--sage-crit)",       bg: "var(--sage-crit-soft)" },
};

function StatusPill({ status }: { status: SessionStatus }): React.ReactElement {
  const cfg = STATUS_CONFIG[status];
  const isProcessing = status === "processing";
  return (
    <span
      className={["rounded-full px-2.5 py-0.5 text-xs font-medium", isProcessing ? "animate-pulse" : ""].join(" ")}
      style={{ color: cfg.color, backgroundColor: cfg.bg }}
    >
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Breadcrumbs
// ---------------------------------------------------------------------------

function Breadcrumbs({ items }: { items: BreadcrumbItem[] }): React.ReactElement {
  const navigate = useNavigate();
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-[var(--sage-text-muted)]">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span aria-hidden="true" className="text-[var(--sage-border)]">/</span>}
          {item.href ? (
            <button
              type="button"
              onClick={() => navigate(item.href!)}
              className="transition-colors hover:text-[var(--sage-text-primary)]"
            >
              {item.label}
            </button>
          ) : (
            <span className="font-medium text-[var(--sage-text-primary)]">{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Theme toggle — sun (light) / moon (dark)
// ---------------------------------------------------------------------------

function ThemeToggle(): React.ReactElement {
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] text-[var(--sage-text-muted)] transition-colors hover:border-[var(--sage-accent)] hover:text-[var(--sage-accent)]"
    >
      {isDark ? (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
          <path d="M10 2a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0v-1.5A.75.75 0 0 1 10 2ZM10 15a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0v-1.5A.75.75 0 0 1 10 15ZM10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM15.657 5.404a.75.75 0 1 0-1.06-1.06l-1.061 1.06a.75.75 0 0 0 1.06 1.06l1.06-1.06ZM6.464 14.596a.75.75 0 1 0-1.06-1.06l-1.06 1.06a.75.75 0 0 0 1.06 1.06l1.06-1.06ZM18 10a.75.75 0 0 1-.75.75h-1.5a.75.75 0 0 1 0-1.5h1.5A.75.75 0 0 1 18 10ZM5 10a.75.75 0 0 1-.75.75h-1.5a.75.75 0 0 1 0-1.5h1.5A.75.75 0 0 1 5 10ZM14.596 15.657a.75.75 0 0 0 1.06-1.06l-1.06-1.061a.75.75 0 1 0-1.06 1.06l1.06 1.06ZM5.404 6.464a.75.75 0 0 0 1.06-1.06L5.404 4.343a.75.75 0 1 0-1.06 1.06l1.06 1.061Z" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
          <path fillRule="evenodd" d="M7.455 2.004a.75.75 0 0 1 .26.77 7 7 0 0 0 9.958 7.967.75.75 0 0 1 1.067.853A8.5 8.5 0 1 1 6.647 1.921a.75.75 0 0 1 .808.083Z" clipRule="evenodd" />
        </svg>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TopBar({
  title,
  status,
  llmProvider,
  breadcrumb,
}: TopBarProps): React.ReactElement {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-[var(--sage-border)] bg-[var(--sage-bg-base)] px-5 transition-colors">

      {/* Left: breadcrumb + title + status */}
      <div className="flex min-w-0 flex-col justify-center">
        {breadcrumb && breadcrumb.length > 0 && (
          <Breadcrumbs items={breadcrumb} />
        )}
        <div className="flex items-center gap-2">
          <h1 className="truncate text-sm font-semibold text-[var(--sage-text-primary)]" style={{ fontFamily: "var(--sage-font-mono)" }}>{title}</h1>
          {status && <StatusPill status={status} />}
        </div>
      </div>

      {/* Right: LLM chip + theme toggle */}
      <div className="flex shrink-0 items-center gap-2">
        {llmProvider && (
          <LLMProviderSelector compact className="hidden sm:block" />
        )}
        <ThemeToggle />
      </div>

    </header>
  );
}
