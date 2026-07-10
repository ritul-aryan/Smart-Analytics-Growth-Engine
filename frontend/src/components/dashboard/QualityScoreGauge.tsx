/**
 * frontend/src/components/dashboard/QualityScoreGauge.tsx
 *
 * Half-circle SVG arc gauge — before / after quality scores.
 * Pure SVG, no Plotly. Uses the --sage-* design tokens.
 *
 * Colour thresholds (Section 8.2):
 *   crit  < 50
 *   high  50–79
 *   good  80+
 *
 * Usage:
 *   <QualityScoreGauge before={34} after={91} />
 *   <QualityScoreGauge before={72} />   — after not yet available
 */

import React from "react";

interface QualityScoreGaugeProps {
  before: number;
  after?: number | null;
  className?: string;
}

function scoreColor(score: number): string {
  if (score >= 80) return "var(--sage-good)";
  if (score >= 50) return "var(--sage-high)";
  return "var(--sage-crit)";
}

function scoreLabel(score: number): string {
  if (score >= 80) return "Good";
  if (score >= 50) return "Fair";
  return "Poor";
}

const RADIUS = 50;
const CIRC   = Math.PI * RADIUS;

interface ArcProps {
  score: number;
  label: string;
}

function GaugeArc({ score, label }: ArcProps): React.ReactElement {
  const clamped = Math.max(0, Math.min(100, score));
  const offset  = CIRC * (1 - clamped / 100);
  const color   = scoreColor(score);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="120" height="72" viewBox="0 0 120 72"
        aria-label={`${label}: ${Math.round(score)}`} role="img">
        {/* Background track */}
        <path
          d="M 10 62 A 50 50 0 0 1 110 62"
          fill="none"
          stroke="var(--sage-border-strong)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Filled arc */}
        <path
          d="M 10 62 A 50 50 0 0 1 110 62"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.9s ease-out" }}
        />
        {/* Score number */}
        <text
          x="60" y="57"
          textAnchor="middle"
          fontSize="20"
          fontWeight="700"
          fontFamily="Inter, system-ui, sans-serif"
          fill={color}
        >
          {Math.round(score)}
        </text>
      </svg>
      <div className="text-center">
        <p className="text-xs font-medium text-[var(--sage-text-muted)]">{label}</p>
        <p className="text-xs font-semibold" style={{ color }}>{scoreLabel(score)}</p>
      </div>
    </div>
  );
}

export default function QualityScoreGauge({
  before,
  after,
  className = "",
}: QualityScoreGaugeProps): React.ReactElement {
  const hasAfter    = after !== null && after !== undefined;
  const improvement = hasAfter ? Math.round((after as number) - before) : null;

  return (
    <div className={className}>
      <div className="flex items-end justify-center gap-4">
        <GaugeArc score={before} label="Before" />

        <div className="mb-10 flex flex-col items-center gap-1">
          <svg className="h-5 w-5 text-[var(--sage-border-strong)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clipRule="evenodd" />
          </svg>
          {improvement !== null && improvement > 0 && (
            <span className="text-xs font-bold text-[var(--sage-good)]">+{improvement}</span>
          )}
          {improvement !== null && improvement < 0 && (
            <span className="text-xs font-bold text-[var(--sage-crit)]">{improvement}</span>
          )}
        </div>

        {hasAfter ? (
          <GaugeArc score={after as number} label="After" />
        ) : (
          <div className="mb-8 flex flex-col items-center gap-1.5">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--sage-border-strong)] border-t-[var(--sage-accent)]" />
            <span className="text-xs text-[var(--sage-text-muted)]">Processing…</span>
          </div>
        )}
      </div>

      <div className="mt-4 flex justify-center gap-4 border-t border-[var(--sage-border)] pt-3 text-xs text-[var(--sage-text-muted)]">
        {[
          { range: "< 50",  label: "Poor", color: "var(--sage-crit)" },
          { range: "50–79", label: "Fair", color: "var(--sage-high)" },
          { range: "80+",   label: "Good", color: "var(--sage-good)" },
        ].map(({ range, label, color }) => (
          <span key={label} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
            {range} {label}
          </span>
        ))}
      </div>
    </div>
  );
}
