/**
 * frontend/src/components/shared/LLMProviderSelector.tsx
 *
 * Gemini / Ollama LLM provider switcher.
 *
 * Reads and writes the active provider via uiStore.  The selected value
 * is sent as `llm_provider` in the POST /api/analyze/start request so
 * users can switch providers per-session without editing .env.
 *
 * Usage:
 *   <LLMProviderSelector />           — full dropdown with labels
 *   <LLMProviderSelector compact />   — compact icon + short name
 */

import React from "react";
import type { LLMProvider } from "../../types/session";
import { useUiStore } from "../../store/uiStore";

// ---------------------------------------------------------------------------
// Provider metadata
// ---------------------------------------------------------------------------

interface ProviderOption {
  value: LLMProvider;
  label: string;
  shortLabel: string;
  description: string;
  badge: string;
  badgeColor: string;
}

const PROVIDERS: ProviderOption[] = [
  {
    value: "gemini-2.0-flash",
    label: "Gemini 2.0 Flash",
    shortLabel: "Gemini 2.0",
    description: "Google's fastest model. Falls back to Ollama if quota is exceeded.",
    badge: "Cloud",
    badgeColor: "bg-[var(--sage-accent-soft)] text-[var(--sage-accent)]",
  },
  {
    value: "ollama",
    label: "Ollama (Offline)",
    shortLabel: "Ollama",
    description: "Fully local. No API key required.",
    badge: "Offline",
    badgeColor: "bg-[var(--sage-good-soft)] text-[var(--sage-good)]",
  },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LLMProviderSelectorProps {
  /**
   * Compact mode: shows only the current provider name + chevron.
   * Clicking opens a dropdown. Default: false (renders full select).
   */
  compact?: boolean;
  /** Extra Tailwind classes for the root element. */
  className?: string;
  /**
   * Called whenever the provider changes, in addition to updating the store.
   * Useful when the parent needs the new value immediately (e.g. UploadPage).
   */
  onChange?: (provider: LLMProvider) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function LLMProviderSelector({
  compact = false,
  className = "",
  onChange,
}: LLMProviderSelectorProps): React.ReactElement {
  const llmProvider = useUiStore((s) => s.llmProvider);
  const setLlmProvider = useUiStore((s) => s.setLlmProvider);

  function handleChange(value: LLMProvider): void {
    setLlmProvider(value);
    onChange?.(value);
  }

  const current = PROVIDERS.find((p) => p.value === llmProvider) ?? PROVIDERS[0];

  if (compact) {
    return (
      <div className={["relative inline-block", className].join(" ")}>
        <select
          value={llmProvider}
          onChange={(e) => handleChange(e.target.value as LLMProvider)}
          aria-label="Select LLM provider"
          className={[
            "cursor-pointer appearance-none rounded-lg border py-1 pl-2.5 pr-7 text-xs font-medium",
            "border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] text-[var(--sage-text-primary)]",
            "hover:border-[var(--sage-accent-border)] focus:outline-none focus:ring-2 focus:ring-[var(--sage-accent)]",
          ].join(" ")}
        >
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.shortLabel}
            </option>
          ))}
        </select>
        <svg
          className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-[var(--sage-text-dim)]"
          viewBox="0 0 12 12"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M6 8L1 3h10L6 8z" />
        </svg>
      </div>
    );
  }

  return (
    <div className={["space-y-1", className].join(" ")}>
      <p className="text-xs font-medium text-[var(--sage-text-muted)] uppercase tracking-wide">
        LLM Provider
      </p>
      <div className="space-y-1.5">
        {PROVIDERS.map((p) => {
          const selected = p.value === llmProvider;
          return (
            <button
              key={p.value}
              type="button"
              onClick={() => handleChange(p.value)}
              className={[
                "w-full rounded-lg border px-3 py-2.5 text-left text-sm transition-colors",
                selected
                  ? "border-[var(--sage-accent-border)] bg-[var(--sage-accent-soft)]"
                  : "border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] hover:border-[var(--sage-accent-border)] hover:bg-[var(--sage-bg-overlay)]",
              ].join(" ")}
            >
              <div className="flex items-center justify-between">
                <span className={["font-medium", selected ? "text-[var(--sage-accent)]" : "text-[var(--sage-text-primary)]"].join(" ")}>
                  {p.label}
                </span>
                <span className={["rounded-full px-1.5 py-0.5 text-xs font-medium", p.badgeColor].join(" ")}>
                  {p.badge}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-[var(--sage-text-muted)]">
                {p.description}
              </p>
            </button>
          );
        })}
      </div>
      <p className="pt-1 text-xs text-[var(--sage-text-dim)]">
        Active: <span className="font-medium text-[var(--sage-text-muted)]">{current.label}</span>
      </p>
    </div>
  );
}
