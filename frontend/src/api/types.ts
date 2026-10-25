/** Mirrors backend/app/schemas/models.py. Keep in sync when the API contract changes. */

export type Status = "MATCHED" | "FORECAST_UNAVAILABLE" | "ACTUAL_MISSING" | "BOTH_MISSING";
export type Resolution = "half_hour" | "hourly";
export type Alignment = "start" | "end";
export type ConflictPolicy = "exclude" | "strict";
export type CoverageLevel = "ok" | "partial" | "low" | "undefined";

export interface Provenance {
  mode: string;
  is_synthetic: boolean;
  retrieved_at: string;
  data_sha256: string;
  period_covered: Record<string, string>;
  sources: Array<Record<string, unknown>>;
  attribution: string;
  attribution_status: string;
  licence_note: string;
  limitations: string[];
  notice?: string | null;
}

export interface ResolvedConfig {
  delivery_start: string;
  delivery_end: string;
  cutoff_time: string;
  cutoff_timezone: string;
  days_before: number;
  availability_lag_minutes: number;
  resolution: Resolution;
  hour_alignment: Alignment;
  conflict_policy: ConflictPolicy;
  top_k: number;
  histogram_bin_mw: number;
}

export interface Counts {
  expected: number;
  actual_observed: number;
  forecast_available: number;
  matched: number;
  forecast_unavailable: number;
  actual_missing: number;
  both_missing: number;
  conflict_affected: number;
  coverage: number | null;
  coverage_level: CoverageLevel;
  unit: "half-hour settlement periods" | "hours";
}

export interface Metrics {
  n: number;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
  p90_abs_error: number | null;
  error_std: number | null;
  mean_actual: number | null;
  mean_forecast: number | null;
  nmae: number | null;
  unit: "MW";
}

export interface ApiWarning {
  code: string;
  severity: "info" | "warning" | "critical";
  message: string;
}

export interface Daily {
  delivery_date: string;
  expected: number;
  matched: number;
  coverage: number | null;
  metrics: Metrics;
}

export interface Extreme {
  start_utc: string;
  start_local: string;
  error_mw: number;
  actual_mw: number;
  forecast_mw: number;
}

export interface Summary {
  scope_notice: string;
  config: ResolvedConfig;
  provenance: Provenance;
  alignment: { value: Alignment; status: "assumed"; note: string };
  cutoff: {
    description: string;
    first_delivery_date: string;
    first_cutoff_utc: string;
    first_cutoff_local: string;
    status: "configurable_assumption";
  };
  resolution_note: string;
  counts: Counts;
  counts_by_resolution: Record<string, Counts>;
  metrics: Metrics;
  daily: Daily[];
  distribution: {
    bin_width_mw: number;
    bins: Array<{ lower_mw: number; upper_mw: number; count: number }>;
    quantiles_mw: Record<string, number> | null;
    over_forecast_count: number;
    under_forecast_count: number;
    exact_count: number;
    error_definition: string;
  };
  under_forecasts: Extreme[];
  over_forecasts: Extreme[];
  elevated_days: string[];
  lead_time_h: Record<string, number> | null;
  vintages_used: number;
  warnings: ApiWarning[];
}

export interface Interval {
  start_utc: string;
  end_utc: string;
  start_local: string;
  delivery_date: string;
  actual_mw: number | null;
  forecast_mw: number | null;
  error_mw: number | null;
  status: Status;
  forecast_published_at: string | null;
  lead_time_h: number | null;
  forecast_row_start: string;
  cutoff_utc: string;
  vintages_total: number;
  vintages_eligible: number;
  vintages_after_cutoff: number;
  unavailable_reason: string | null;
  conflict_fallback: boolean;
  conflict_involved: boolean;
  actual_conflict: boolean;
}

export interface Intervals {
  scope_notice: string;
  config: ResolvedConfig;
  provenance: Provenance;
  alignment: Summary["alignment"];
  resolution_note: string;
  counts: Counts;
  intervals: Interval[];
}

export interface Vintage {
  publish_utc: string;
  forecast_mw: number | null;
  lead_time_h: number;
  relative_to_cutoff_min: number;
  eligible: boolean;
  selected: boolean;
  error_if_used_mw: number | null;
  note: string;
}

export interface Revisions {
  scope_notice: string;
  config: ResolvedConfig;
  interval: Interval;
  forecast_row_start: string;
  hour_start: string;
  cutoff_utc: string;
  vintages: Vintage[];
  conflicted_vintages: Array<{ publish_utc: string; values_mw: Array<number | null>; row_count: number }>;
  explanation: string[];
  alignment: Summary["alignment"];
}

export interface Bucket {
  label: string;
  metrics: Metrics;
}

export interface Scenarios {
  scope_notice: string;
  config: ResolvedConfig;
  provenance: Provenance;
  disclaimer: string;
  caveats: string[];
  sample: { matched_intervals: number; delivery_days: number; unit: string };
  level_offset_mw: number | null;
  error_std_mw: number | null;
  buffers: Array<{
    confidence_pct: number;
    buffer_mw: number;
    raw_quantile_mw: number;
    energy_mwh_per_interval_if_sustained: number;
  }>;
  bands: Array<{ confidence_pct: number; lower_mw: number; upper_mw: number }>;
  by_hour_of_day: Bucket[];
  by_lead_time: Bucket[];
  by_forecast_level: Bucket[];
  elevated_days: string[];
  rolling_origin: Array<{
    confidence_pct: number;
    realised_pct: number | null;
    evaluated_days: number;
    skipped_days: number;
    days: Array<{ delivery_date: string; history_days: number; buffer_mw: number; n: number; within_buffer: number }>;
  }>;
  interval_unit: string;
}

export interface ScopeDiagnostic {
  headline: string;
  body: string;
  evidence: Record<string, number>;
  source: string;
  measured_on: string;
  not_established: string[];
}

export interface DataQuality {
  config: ResolvedConfig;
  provenance: Provenance;
  sources: Array<Record<string, unknown>>;
  counts: Counts;
  counts_by_resolution: Record<string, Counts>;
  normalisation: Record<string, Record<string, unknown>>;
  conflicts: Array<Record<string, unknown>>;
  conflict_total: number;
  vintage_stats: Record<string, unknown>;
  anomalies: Array<{ type: string; detail: string; date?: string; instances?: string[] }>;
  assumptions: string[];
  limitations: string[];
  scope_diagnostic: ScopeDiagnostic;
  partial_hour_sps: number;
  unexpected_actual_rows: number;
}

export interface Meta {
  app_version: string;
  purpose: string;
  permitted_window: { start: string; end: string };
  defaults: ResolvedConfig;
  cutoff_presets: Array<{ id: string; label: string; time: string; timezone: string; status: string; basis: string }>;
  resolutions: Array<{ id: string; label: string; note: string }>;
  alignment_options: Array<{ id: string; label: string; status: string; note: string }>;
  conflict_policies: Array<{ id: string; label: string; note: string }>;
  datasets: Array<{ id: string; role: string; description: string; documentation: string; resolution: string }>;
  provenance: Provenance;
  attribution: string;
  attribution_status: string;
  scope_diagnostic: ScopeDiagnostic;
  error_convention: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Array<{ field?: string | null; message: string }> };
}
