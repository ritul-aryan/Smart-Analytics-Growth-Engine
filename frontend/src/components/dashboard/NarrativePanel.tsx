/**
 * frontend/src/components/dashboard/NarrativePanel.tsx
 *
 * EDA narrative hero card — shown prominently at the top of the Overview tab.
 *
 * Sections (left-to-right on wide screens, stacked on mobile):
 *   • ML Readiness score     — large number + half-circle arc + notes
 *   • Recommendation         — intent-aligned next-step text
 *   • Top correlations       — Spearman r pairs with progress bars
 *   • Missingness hotspots   — columns with highest null rate + bars
 */

import React from "react";
import type { EdaNarrative } from "../../types/chart";

interface NarrativePanelProps {
  narrative: EdaNarrative;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readinessColor(score: number): string {
  if (score >= 80) return "var(--sage-good)";
  if (score >= 50) return "var(--sage-high)";
  return "var(--sage-crit)";
}

/** Soft (translucent) fill matching readinessColor — for pill backgrounds. */
function readinessSoftColor(score: number): string {
  if (score >= 80) return "var(--sage-good-soft)";
  if (score >= 50) return "var(--sage-high-soft)";
  return "var(--sage-crit-soft)";
}

function readinessLabel(score: number): string {
  if (score >= 80) return "Good";
  if (score >= 50) return "Fair";
  return "Poor";
}

const RADIUS = 52;
const CIRC   = Math.PI * RADIUS;

function ReadinessArc({ score }: { score: number }): React.ReactElement {
  const clamped = Math.max(0, Math.min(100, score));
  const offset  = CIRC * (1 - clamped / 100);
  const color   = readinessColor(score);
  return (
    <svg width="140" height="82" viewBox="0 0 140 82" aria-label={`ML readiness: ${score}`} role="img">
      <path d="M 14 74 A 56 56 0 0 1 126 74" fill="none" stroke="var(--sage-border-strong)" strokeWidth="10" strokeLinecap="round" />
      <path
        d="M 14 74 A 56 56 0 0 1 126 74"
        fill="none"
        stroke={color}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={CIRC}
        strokeDashoffset={offset}
        style={{ transition: "stroke-dashoffset 0.9s ease-out" }}
      />
      <text x="70" y="68" textAnchor="middle" fontSize="22" fontWeight="700"
        fontFamily="Inter, system-ui, sans-serif" fill={color}>
        {Math.round(score)}
      </text>
    </svg>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }): React.ReactElement {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[var(--sage-text-muted)]">{title}</p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function NarrativePanel({ narrative }: NarrativePanelProps): React.ReactElement {
  const {
    ml_readiness_score, ml_readiness_notes,
    top_correlations, missingness_hotspots,
    intent_recommendation,
    row_count, col_count, numeric_cols, categorical_cols, datetime_cols,
  } = narrative;

  return (
    <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]">

      {/* Header */}
      <div className="flex items-center gap-3 border-b border-[var(--sage-border)] px-5 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent-soft)]">
          <svg className="h-4 w-4 text-[var(--sage-accent)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
          </svg>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-[var(--sage-text-primary)]">EDA Narrative</h2>
          <p className="text-xs text-[var(--sage-text-muted)]">
            {row_count.toLocaleString()} rows · {col_count} columns (after feature engineering)
            {numeric_cols.length > 0    && ` · ${numeric_cols.length} numeric`}
            {categorical_cols.length > 0 && ` · ${categorical_cols.length} categorical`}
            {datetime_cols.length > 0   && ` · ${datetime_cols.length} datetime`}
          </p>
        </div>
      </div>

      {/* Body — 4-column grid on xl, 2-col on md, 1-col on mobile */}
      <div className="grid grid-cols-1 gap-6 p-5 md:grid-cols-2 xl:grid-cols-4">

        {/* ML Readiness */}
        <Section title="ML Readiness">
          <div className="flex flex-col items-center">
            <ReadinessArc score={ml_readiness_score} />
            <span
              className="mt-1 rounded-full px-3 py-0.5 text-xs font-semibold"
              style={{ color: readinessColor(ml_readiness_score), backgroundColor: readinessSoftColor(ml_readiness_score) }}
            >
              {readinessLabel(ml_readiness_score)} · {ml_readiness_score.toFixed(1)} / 100
            </span>
            {ml_readiness_notes.length > 0 && (
              <ul className="mt-3 w-full space-y-1.5">
                {ml_readiness_notes.map((n, i) => (
                  <li key={i} className="flex gap-1.5 text-xs text-[var(--sage-high)]">
                    <span className="shrink-0">⚠</span><span>{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>

        {/* Recommendation */}
        <Section title="Recommendation">
          <p className="text-sm leading-relaxed text-[var(--sage-text-primary)]">{intent_recommendation}</p>
        </Section>

        {/* Top Correlations */}
        <Section title="Top Correlations">
          {top_correlations.length === 0 ? (
            <p className="text-xs text-[var(--sage-text-muted)]">No strong correlations found.</p>
          ) : (
            <div className="space-y-3">
              {top_correlations.map((c, i) => {
                const isPos = c.spearman_r >= 0;
                const pct   = Math.abs(c.spearman_r) * 100;
                return (
                  <div key={i}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="max-w-[120px] truncate font-mono text-[var(--sage-text-primary)]">{c.col_a} × {c.col_b}</span>
                      <span className={["font-semibold", isPos ? "text-[var(--sage-accent)]" : "text-[var(--sage-crit)]"].join(" ")}>
                        {isPos ? "+" : ""}{c.spearman_r.toFixed(2)}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--sage-bg-overlay)]">
                      <div className={["h-full rounded-full", isPos ? "bg-[var(--sage-accent)]" : "bg-[var(--sage-crit)]"].join(" ")} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Section>

        {/* Missingness */}
        <Section title="Missingness Hotspots">
          {missingness_hotspots.length === 0 ? (
            <p className="text-xs text-[var(--sage-text-muted)]">No missing data detected.</p>
          ) : (
            <div className="space-y-3">
              {missingness_hotspots.map((h, i) => {
                const pct   = h.null_rate * 100;
                const color = h.null_rate > 0.4 ? "var(--sage-crit)" : "var(--sage-high)";
                return (
                  <div key={i}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="max-w-[120px] truncate font-mono text-[var(--sage-text-primary)]">{h.column}</span>
                      <span className="font-semibold tabular-nums" style={{ color }}>{pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--sage-bg-overlay)]">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Section>

      </div>
    </div>
  );
}
