/**
 * frontend/src/pages/SettingsPage.tsx
 *
 * Route: /settings
 *
 * Lets the user pick their active LLM provider and store API keys.
 * Keys are saved to Zustand (persisted to localStorage); they are never
 * sent to the backend directly -- the frontend injects them into requests.
 *
 * Ollama is self-hosted and never requires an API key; its key row is
 * intentionally omitted from the form.
 */

import React, { useState } from "react";
import { useUiStore } from "../store/uiStore";
import type { ActiveProvider } from "../store/uiStore";
import ThemeToggle from "../components/shared/ThemeToggle";

// ---------------------------------------------------------------------------
// Provider metadata
// ---------------------------------------------------------------------------

interface ProviderMeta {
  id: ActiveProvider;
  name: string;
  tagline: string;
  needsKey: boolean;
  keyPlaceholder: string;
  icon: React.ReactElement;
  comingSoon?: boolean;
}

function GeminiIcon({ size = 20 }: { size?: number }): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5L12 2z"
        fill="#4285F4"
      />
    </svg>
  );
}

function ClaudeIcon({ size = 20 }: { size?: number }): React.ReactElement {
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

function OllamaIcon({ size = 20 }: { size?: number }): React.ReactElement {
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

const PROVIDERS: ProviderMeta[] = [
  {
    id: "gemini",
    name: "Google Gemini",
    tagline: "Gemini 2.0 Flash via Google AI Studio",
    needsKey: true,
    keyPlaceholder: "AIza...",
    icon: <GeminiIcon size={22} />,
  },
  {
    id: "claude",
    name: "Anthropic Claude",
    tagline: "Claude Sonnet via Anthropic API",
    needsKey: true,
    keyPlaceholder: "sk-ant-...",
    icon: <ClaudeIcon size={22} />,
    comingSoon: true,
  },
  {
    id: "ollama",
    name: "Ollama (local)",
    tagline: "Self-hosted models — no API key required",
    needsKey: false,
    keyPlaceholder: "",
    icon: <OllamaIcon size={22} />,
  },
];

// ---------------------------------------------------------------------------
// Key input with show/hide toggle
// ---------------------------------------------------------------------------

function ApiKeyInput({
  value,
  placeholder,
  onChange,
}: {
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
}): React.ReactElement {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative mt-2 flex items-center">
      <input
        type={visible ? "text" : "password"}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        spellCheck={false}
        className={[
          "w-full rounded-lg py-2 pl-3 pr-10 text-sm font-mono",
          "bg-[var(--sage-bg-base)] text-[var(--sage-text-primary)]",
          "border border-[var(--sage-border)] outline-none",
          "placeholder:text-[var(--sage-text-muted)]",
          "focus:border-[var(--sage-accent)] focus:ring-1 focus:ring-[var(--sage-accent)]",
        ].join(" ")}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide API key" : "Show API key"}
        className="absolute right-2.5 text-[var(--sage-text-muted)] hover:text-[var(--sage-text-primary)]"
      >
        {visible ? (
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
            <path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M3.28 2.22a.75.75 0 00-1.06 1.06l14.5 14.5a.75.75 0 101.06-1.06L3.28 2.22zM6.25 7.31l1.47 1.47A3.001 3.001 0 0010 13a3.001 3.001 0 001.22-5.72l-1.47-1.47A3 3 0 006.25 7.31zM7.53 12.53A5.978 5.978 0 014.07 10c.768-2.44 3.04-4.214 5.6-4.473L8.2 4.055C4.585 4.467 1.733 7.223.458 10c.917 2.923 3.196 5.272 6.036 6.326l1.037-3.796zM13.75 12.69l-1.47-1.47A3 3 0 009.78 7.31L8.31 5.84A5.977 5.977 0 0115.93 10c-.768 2.44-3.04 4.214-5.6 4.473l1.473 1.473c3.613-.412 6.465-3.168 7.74-5.946-.917-2.923-3.196-5.272-6.036-6.326l-1.037 3.796z" clipRule="evenodd" />
          </svg>
        )}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provider card
// ---------------------------------------------------------------------------

function ProviderCard({
  meta,
  active,
  apiKey,
  onSelect,
  onKeyChange,
}: {
  meta: ProviderMeta;
  active: boolean;
  apiKey: string;
  onSelect: () => void;
  onKeyChange: (v: string) => void;
}): React.ReactElement {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => { if (meta.comingSoon) return; onSelect(); }}
      onKeyDown={(e) => {
        if (meta.comingSoon) return;
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); }
      }}
      aria-disabled={meta.comingSoon ? true : undefined}
      className={[
        "rounded-xl border p-4 transition-all",
        meta.comingSoon
          ? "cursor-not-allowed opacity-60 border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]"
          : [
              "cursor-pointer",
              active
                ? "border-[var(--sage-accent)] ring-1 ring-[var(--sage-accent)] bg-[var(--sage-bg-elevated)]"
                : "border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] hover:border-[var(--sage-accent-border)]",
            ].join(" "),
      ].join(" ")}
    >
      {/* Card header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {meta.icon}
          <div>
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-[var(--sage-text-primary)]">{meta.name}</p>
              {meta.comingSoon && (
                <span className="rounded bg-[var(--sage-border)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--sage-text-muted)]">
                  Coming soon
                </span>
              )}
            </div>
            <p className="text-xs text-[var(--sage-text-muted)]">{meta.tagline}</p>
          </div>
        </div>

        {/* Radio dot */}
        <div
          className={[
            "h-4 w-4 shrink-0 rounded-full border-2",
            active
              ? "border-[var(--sage-accent)] bg-[var(--sage-accent)]"
              : "border-[var(--sage-border)]",
          ].join(" ")}
          aria-hidden="true"
        />
      </div>

      {/* Key input — shown only when this provider is active, needs a key, and is not comingSoon */}
      {active && meta.needsKey && !meta.comingSoon && (
        <div onClick={(e) => e.stopPropagation()}>
          <label className="mt-3 block text-xs font-medium text-[var(--sage-text-muted)]">
            API Key
          </label>
          <ApiKeyInput
            value={apiKey}
            placeholder={meta.keyPlaceholder}
            onChange={onKeyChange}
          />
          <p className="mt-1 text-xs text-[var(--sage-text-muted)]">
            Stored locally in your browser. Never transmitted to our servers.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SettingsPage(): React.ReactElement {
  const activeProvider  = useUiStore((s) => s.activeProvider);
  const apiKeys         = useUiStore((s) => s.apiKeys);
  const setActiveProvider = useUiStore((s) => s.setActiveProvider);
  const setApiKey       = useUiStore((s) => s.setApiKey);
  const analysisSettings     = useUiStore((s) => s.analysisSettings);
  const setAnalysisSettings  = useUiStore((s) => s.setAnalysisSettings);
  const resetAnalysisSettings = useUiStore((s) => s.resetAnalysisSettings);

  return (
    <main className="flex flex-1 flex-col overflow-y-auto px-6 py-10">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--sage-accent-soft)]">
            <svg className="h-5 w-5 text-[var(--sage-accent)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-[var(--sage-text-primary)]">Settings</h1>
            <p className="text-sm text-[var(--sage-text-muted)]">
              Choose your LLM provider and configure API access.
            </p>
          </div>
        </div>

        <div className="mt-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--sage-text-muted)]">
            LLM Provider
          </h2>

          <div className="flex flex-col gap-3">
            {PROVIDERS.map((meta) => (
              <ProviderCard
                key={meta.id}
                meta={meta}
                active={activeProvider === meta.id}
                apiKey={apiKeys[meta.id]}
                onSelect={() => setActiveProvider(meta.id)}
                onKeyChange={(v) => setApiKey(meta.id, v)}
              />
            ))}
          </div>
        </div>

        <div className="mt-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--sage-text-muted)]">
            Appearance
          </h2>
          <div className="flex items-center justify-between rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-4">
            <div>
              <p className="text-sm font-semibold text-[var(--sage-text-primary)]">Theme</p>
              <p className="text-xs text-[var(--sage-text-muted)]">Switch between light and dark mode.</p>
            </div>
            <ThemeToggle showLabel />
          </div>
        </div>

        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--sage-text-muted)]">
              Analysis defaults
            </h2>
            <button
              type="button"
              onClick={resetAnalysisSettings}
              className="text-xs text-[var(--sage-accent)] underline hover:opacity-80"
            >
              Reset to defaults
            </button>
          </div>
          <div className="flex flex-col gap-4 rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)] p-4">
            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm text-[var(--sage-text-primary)]">OHE max unique values</label>
                <span className="text-sm font-mono text-[var(--sage-text-muted)]">{analysisSettings.oheMaxUnique}</span>
              </div>
              <input
                type="range" min={2} max={50} step={1}
                value={analysisSettings.oheMaxUnique}
                onChange={(e) => setAnalysisSettings({ oheMaxUnique: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--sage-accent)]"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm text-[var(--sage-text-primary)]">Log transform skew threshold</label>
                <span className="text-sm font-mono text-[var(--sage-text-muted)]">{analysisSettings.logSkewThreshold}</span>
              </div>
              <input
                type="range" min={0.5} max={5.0} step={0.1}
                value={analysisSettings.logSkewThreshold}
                onChange={(e) => setAnalysisSettings({ logSkewThreshold: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--sage-accent)]"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm text-[var(--sage-text-primary)]">Interaction term |r| threshold</label>
                <span className="text-sm font-mono text-[var(--sage-text-muted)]">{analysisSettings.correlationThreshold}</span>
              </div>
              <input
                type="range" min={0.1} max={0.99} step={0.01}
                value={analysisSettings.correlationThreshold}
                onChange={(e) => setAnalysisSettings({ correlationThreshold: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--sage-accent)]"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm text-[var(--sage-text-primary)]">Outlier IQR multiplier</label>
                <span className="text-sm font-mono text-[var(--sage-text-muted)]">{analysisSettings.outlierIqrMultiplier}</span>
              </div>
              <input
                type="range" min={1.5} max={5.0} step={0.1}
                value={analysisSettings.outlierIqrMultiplier}
                onChange={(e) => setAnalysisSettings({ outlierIqrMultiplier: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--sage-accent)]"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm text-[var(--sage-text-primary)]">Null density row threshold</label>
                <span className="text-sm font-mono text-[var(--sage-text-muted)]">{analysisSettings.nullDensityThreshold}</span>
              </div>
              <input
                type="range" min={0.1} max={0.9} step={0.05}
                value={analysisSettings.nullDensityThreshold}
                onChange={(e) => setAnalysisSettings({ nullDensityThreshold: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--sage-accent)]"
              />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
