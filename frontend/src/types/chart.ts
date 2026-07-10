/**
 * frontend/src/types/chart.ts
 *
 * Types for Plotly chart specs and the EDA portfolio produced by the
 * Storyteller agent in Phase 3.  PlotlyConfig mirrors the Plotly.js
 * Data + Layout structure so components can pass it directly to Plotly.
 *
 * Field names mirror the backend ChartOut Pydantic model exactly.
 */

// ---------------------------------------------------------------------------
// Plotly config wrapper
// @types/plotly.js uses UMD namespace exports which cannot be default-imported.
// We use `any` here; Plotly renders correctly at runtime regardless.
// ---------------------------------------------------------------------------

export interface PlotlyConfig {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: Record<string, any>;
}

// ---------------------------------------------------------------------------
// Chart entity (mirrors backend ChartOut / charts table)
// ---------------------------------------------------------------------------

export interface ChartSpec {
  id: string;
  session_id: string;
  chart_type: string;
  title: string;
  plotly_config: PlotlyConfig;
  insight_text: string | null;
  columns_used: string[];
  display_order: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// EDA narrative sub-types
// ---------------------------------------------------------------------------

export interface Correlation {
  col_a: string;
  col_b: string;
  spearman_r: number;
}

export interface MissingnessHotspot {
  column: string;
  null_rate: number;
}

// ---------------------------------------------------------------------------
// Column stats (canonical definition -- ColumnStatsTable re-exports this)
// ---------------------------------------------------------------------------

export interface ColumnStat {
  name: string;
  dtype: string;
  null_count: number;
  null_rate: number;
  unique_count: number;
  mean: number | null;
  std: number | null;
  min: number | null;
  max: number | null;
  skewness: number | null;
  kurtosis: number | null;
}

// ---------------------------------------------------------------------------
// EDA narrative (Phase 3 Storyteller output)
// ---------------------------------------------------------------------------

export interface EdaNarrative {
  top_correlations: Correlation[];
  missingness_hotspots: MissingnessHotspot[];
  column_stats: ColumnStat[];
  anomaly_notes: string[];
  ml_readiness_score: number;
  ml_readiness_notes: string[];
  intent_recommendation: string;
  row_count: number;
  col_count: number;
  numeric_cols: string[];
  categorical_cols: string[];
  datetime_cols: string[];
}
