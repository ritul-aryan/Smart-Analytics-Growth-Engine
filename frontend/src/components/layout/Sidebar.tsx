/**
 * frontend/src/components/layout/Sidebar.tsx
 *
 * Persistent left sidebar — theme-aware via CSS variables.
 * Collapses to an icon rail on narrow screens or via toggle button.
 *
 * Provider status widget (bottom):
 *   expanded  — provider icon + name + green "Connected" pill
 *   collapsed — provider icon only with a green dot at the corner
 */

import React from "react";
import { useNavigate } from "react-router-dom";
import { useUiStore } from "../../store/uiStore";
import type { ActiveProvider } from "../../store/uiStore";
import SessionHistory from "../shared/SessionHistory";

// ---------------------------------------------------------------------------
// Logo
// ---------------------------------------------------------------------------

function Logo(): React.ReactElement {
  return (
    <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--sage-accent)" />
      <line x1="10" y1="22" x2="10" y2="16" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="16" y1="22" x2="16" y2="10" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="22" y1="22" x2="22" y2="13" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Collapse toggle
// ---------------------------------------------------------------------------

function CollapseBtn({ collapsed, onClick }: { collapsed: boolean; onClick: () => void }): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--sage-text-muted)] transition-colors hover:bg-[var(--sage-border)] hover:text-[var(--sage-text-primary)]"
    >
      <svg
        viewBox="0 0 16 16"
        className={["h-4 w-4 transition-transform", collapsed ? "rotate-180" : ""].join(" ")}
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M9.78 4.22a.75.75 0 010 1.06L7.06 8l2.72 2.72a.75.75 0 11-1.06 1.06L5.47 8.53a.75.75 0 010-1.06L8.72 4.22a.75.75 0 011.06 0z" />
      </svg>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Nav item
// ---------------------------------------------------------------------------

function NavItem({
  icon,
  label,
  collapsed,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  collapsed: boolean;
  onClick?: () => void;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
        "text-[var(--sage-text-muted)] hover:bg-[var(--sage-border)]/40 hover:text-[var(--sage-text-primary)]",
        collapsed ? "justify-center" : "",
      ].join(" ")}
    >
      <span className="shrink-0">{icon}</span>
      {!collapsed && <span className="truncate">{label}</span>}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Provider icons (inline SVG, no external deps)
// ---------------------------------------------------------------------------

function GeminiIcon({ size = 16 }: { size?: number }): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5L12 2z"
        fill="#4285F4"
      />
    </svg>
  );
}

function ClaudeIcon({ size = 16 }: { size?: number }): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="#D97757" />
      <text
        x="12" y="16"
        textAnchor="middle"
        fontSize="11"
        fontWeight="700"
        fill="white"
        fontFamily="sans-serif"
      >C</text>
    </svg>
  );
}

function OllamaIcon({ size = 16 }: { size?: number }): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="4" fill="#22C55E" />
      <path
        d="M7 8h2v2H7V8zm4 0h2v2h-2V8zm4 0h2v2h-2V8zM7 12h10v1H7v-1zm0 3h8v1H7v-1z"
        fill="white"
      />
    </svg>
  );
}

const PROVIDER_LABEL: Record<ActiveProvider, string> = {
  gemini: "Gemini",
  claude: "Claude",
  ollama: "Ollama",
};

function ProviderIcon({ provider, size = 16 }: { provider: ActiveProvider; size?: number }): React.ReactElement {
  if (provider === "claude")  return <ClaudeIcon size={size} />;
  if (provider === "ollama")  return <OllamaIcon size={size} />;
  return <GeminiIcon size={size} />;
}

// ---------------------------------------------------------------------------
// Provider status widget
// ---------------------------------------------------------------------------

function ProviderStatusWidget({ collapsed }: { collapsed: boolean }): React.ReactElement {
  const activeProvider = useUiStore((s) => s.activeProvider);

  if (collapsed) {
    return (
      <div className="flex justify-center py-3">
        <div className="relative inline-flex">
          <ProviderIcon provider={activeProvider} size={20} />
          {/* Green status dot */}
          <span
            className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-[var(--sage-good)] ring-1 ring-[var(--sage-bg-panel)]"
            aria-label="Connected"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5 px-3 py-3">
      <ProviderIcon provider={activeProvider} size={18} />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-[var(--sage-text-primary)] leading-none">
          {PROVIDER_LABEL[activeProvider]}
        </p>
        <p className="mt-0.5 flex items-center gap-1 text-xs text-[var(--sage-good)] leading-none">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--sage-good)]" aria-hidden="true" />
          Connected
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Settings icon
// ---------------------------------------------------------------------------

function SettingsIcon(): React.ReactElement {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
        clipRule="evenodd"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Sidebar(): React.ReactElement {
  const collapsed     = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const navigate      = useNavigate();

  return (
    <aside
      className={[
        "sticky top-0 flex h-screen flex-col border-r transition-all duration-200",
        "border-[var(--sage-border)] bg-[var(--sage-bg-panel)]",
        collapsed ? "w-14" : "w-60",
      ].join(" ")}
    >
      {/* Header */}
      <div
        className={[
          "flex shrink-0 items-center",
          collapsed ? "flex-col gap-2 px-0 py-3" : "h-14 justify-between px-3",
        ].join(" ")}
      >
        <button
          type="button"
          onClick={() => navigate("/")}
          className="flex items-center gap-2.5 focus:outline-none"
          aria-label="Go to home"
        >
          <Logo />
          {!collapsed && (
            <span className="text-sm font-bold tracking-tight text-[var(--sage-text-primary)]">SAGE</span>
          )}
        </button>
        <CollapseBtn collapsed={collapsed} onClick={toggleSidebar} />
      </div>

      <div className="mx-3 h-px bg-[var(--sage-border)]" />

      {/* Nav */}
      <nav className="px-2 py-3">
        <NavItem
          collapsed={collapsed}
          onClick={() => navigate("/")}
          label="New Analysis"
          icon={
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
            </svg>
          }
        />
        <NavItem
          collapsed={collapsed}
          onClick={() => navigate("/settings")}
          label="Settings"
          icon={<SettingsIcon />}
        />
      </nav>

      <div className="mx-3 h-px bg-[var(--sage-border)]" />

      {/* Session history */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden py-3">
        {!collapsed && (
          <>
            <p className="mb-1.5 shrink-0 px-3 text-xs font-semibold uppercase tracking-widest text-[var(--sage-text-muted)]">
              History
            </p>
            <SessionHistory />
          </>
        )}
      </div>

      <div className="mx-3 h-px bg-[var(--sage-border)]" />

      {/* Provider status widget */}
      <ProviderStatusWidget collapsed={collapsed} />

      <div className="mx-3 h-px bg-[var(--sage-border)]" />

      {/* Version */}
      {!collapsed && (
        <div className="px-3 py-3">
          <span className="text-xs text-[var(--sage-text-muted)]">SAGE : Smart Analytics & Growth Engine</span>
        </div>
      )}
    </aside>
  );
}
