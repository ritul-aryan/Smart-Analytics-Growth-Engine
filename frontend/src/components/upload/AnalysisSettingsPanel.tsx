/**
 * frontend/src/components/upload/AnalysisSettingsPanel.tsx
 *
 * Collapsible panel exposing user-configurable analysis settings (Section 8.3).
 * All values are stored in uiStore (persisted to localStorage) and sent with
 * every POST /api/analyze/start request.
 *
 * Settings:
 *   oheMaxUnique         — OHE cardinality ceiling (2–50, default 10)
 *   logSkewThreshold     — Log transform skewness gate (0.5–5.0, default 1.5)
 *   correlationThreshold — Interaction term |r| floor (0.1–0.99, default 0.50)
 *   outlierIqrMultiplier — IQR multiplier for outlier detection (1.5–5.0, default 3.0)
 *   nullDensityThreshold — Row null fraction gate (0.1–0.9, default 0.50)
 */

import React, { useState } from "react";
import { useUiStore, DEFAULT_ANALYSIS_SETTINGS } from "../../store/uiStore";

interface SliderRowProps {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled: boolean;
  onChange: (v: number) => void;
}

function SliderRow({ label, hint, value, min, max, step, disabled, onChange }: SliderRowProps): React.ReactElement {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-[var(--sage-text-muted)]">{label}</span>
        <span className="tabular-nums text-[var(--sage-text-primary)]">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer accent-[var(--sage-accent)] disabled:cursor-not-allowed disabled:opacity-50"
        aria-label={label}
      />
      <p className="text-[10px] text-[var(--sage-text-dim)]">{hint}</p>
    </div>
  );
}

interface Props {
  disabled: boolean;
}

export default function AnalysisSettingsPanel({ disabled }: Props): React.ReactElement {
  const [open, setOpen] = useState(false);
  const settings       = useUiStore((s) => s.analysisSettings);
  const setSettings    = useUiStore((s) => s.setAnalysisSettings);
  const resetSettings  = useUiStore((s) => s.resetAnalysisSettings);

  const isDefault = JSON.stringify(settings) === JSON.stringify(DEFAULT_ANALYSIS_SETTINGS);

  return (
    <div className="rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-overlay)]">
      {/* Toggle header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-[var(--sage-text-muted)]"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          Advanced settings
          {!isDefault && (
            <span className="rounded-full bg-[var(--sage-accent-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--sage-accent)]">
              modified
            </span>
          )}
        </span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={["h-4 w-4 text-[var(--sage-text-dim)] transition-transform", open ? "rotate-180" : ""].join(" ")}
          aria-hidden="true"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-[var(--sage-border)] px-4 py-4 space-y-4">
          <SliderRow
            label="OHE max unique values"
            hint="Controls which categorical (text) columns get one-hot encoded into 0/1 columns for machine learning. Columns with more unique values than this are skipped instead, since one-hot encoding a column with hundreds of unique values would create hundreds of new columns. Example: a 'city' column with 8 distinct cities gets encoded; a 'patient_id' column with 50,000 unique values gets skipped. Default: 10."
            value={settings.oheMaxUnique}
            min={2} max={50} step={1}
            disabled={disabled}
            onChange={(v) => setSettings({ oheMaxUnique: v })}
          />
          <SliderRow
            label="Log transform skew threshold"
            hint="Skewness measures how lopsided a column's distribution is — 0 means perfectly symmetric, larger values mean a long tail on one side. When a column's skewness (positive or negative) exceeds this threshold, SAGE adds a log-transformed version of it, which often makes lopsided data easier for models to learn from. Example: income data is often heavily right-skewed (skew > 1.5) because most people earn a moderate amount but a few earn very high salaries. Default: 1.5."
            value={settings.logSkewThreshold}
            min={0.5} max={5.0} step={0.1}
            disabled={disabled}
            onChange={(v) => setSettings({ logSkewThreshold: v })}
          />
          <SliderRow
            label="Interaction term |r| threshold"
            hint="An interaction term is a new column created by multiplying two existing numeric columns together, which can help models capture relationships that neither column shows on its own. SAGE only creates one when the strongest correlation between two columns (as an absolute value, ignoring direction) exceeds this threshold. Example: if 'height' and 'weight' correlate at 0.62, a height×weight interaction column is added. Default: 0.50."
            value={settings.correlationThreshold}
            min={0.1} max={0.99} step={0.01}
            disabled={disabled}
            onChange={(v) => setSettings({ correlationThreshold: v })}
          />
          <SliderRow
            label="Outlier IQR multiplier"
            hint="Outliers are flagged using the IQR (interquartile range) method: any value farther from the middle 50% of the data than this multiplier times the IQR is flagged as an outlier. A higher multiplier means only more extreme values get flagged; a lower multiplier flags more values, including moderate ones. Example: with the default of 3.0, a value has to be quite far from the typical range to be flagged — raising it to 5.0 would only catch the most extreme cases. Default: 3.0."
            value={settings.outlierIqrMultiplier}
            min={1.5} max={5.0} step={0.1}
            disabled={disabled}
            onChange={(v) => setSettings({ outlierIqrMultiplier: v })}
          />
          <SliderRow
            label="Null density row threshold"
            hint="If a single row is missing more than this fraction of its values, it's flagged as a high-null-density row — often a sign the whole row should be reviewed rather than filled in column by column. Example: with the default of 0.50, a row missing 6 out of 10 fields gets flagged; a row missing only 2 out of 10 does not. Default: 0.50."
            value={settings.nullDensityThreshold}
            min={0.1} max={0.9} step={0.05}
            disabled={disabled}
            onChange={(v) => setSettings({ nullDensityThreshold: v })}
          />

          {!isDefault && (
            <button
              type="button"
              onClick={resetSettings}
              disabled={disabled}
              className="text-xs text-[var(--sage-text-muted)] underline hover:text-[var(--sage-text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Reset to defaults
            </button>
          )}
        </div>
      )}
    </div>
  );
}
