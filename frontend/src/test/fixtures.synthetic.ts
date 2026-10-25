/**
 * SYNTHETIC TEST FIXTURES. Invented values used only by component tests; they are NOT Elexon observations
 * and are never bundled into the application. Typed against the real API types so contract drift fails tsc.
 */
import type {
  Counts,
  DataQuality,
  Interval,
  Intervals,
  Meta,
  Metrics,
  Provenance,
  Revisions,
  Scenarios,
  Summary,
} from "@/api/types";

export const SYNTHETIC_NOTE = "SYNTHETIC TEST FIXTURE";

export const provenance = (over: Partial<Provenance> = {}): Provenance => ({
  mode: "snapshot",
  is_synthetic: false,
  retrieved_at: "2026-10-25T11:06:27Z",
  data_sha256: "a".repeat(64),
  period_covered: { delivery_start: "2026-01-01", delivery_end: "2026-01-31" },
  sources: [{ dataset: "FUELHH" }, { dataset: "WINDFOR" }],
  attribution: "Contains BMRS data (c) Elexon Limited copyright and database right.",
  licence_note: "Third-party data.",
  limitations: ["Fixture limitation"],
  notice: null,
  ...over,
});

export const counts = (over: Partial<Counts> = {}): Counts => ({
  expected: 96,
  actual_observed: 96,
  forecast_available: 96,
  matched: 96,
  forecast_unavailable: 0,
  actual_missing: 0,
  both_missing: 0,
  conflict_affected: 0,
  coverage: 1,
  coverage_level: "ok",
  unit: "half-hour settlement periods",
  ...over,
});

export const metrics = (over: Partial<Metrics> = {}): Metrics => ({
  n: 96,
  mae: 150,
  rmse: 200,
  bias: -120,
  p90_abs_error: 320,
  error_std: 160,
  mean_actual: 5000,
  mean_forecast: 5120,
  nmae: 0.03,
  unit: "MW",
  ...over,
});

const config = {
  delivery_start: "2026-01-01",
  delivery_end: "2026-01-02",
  cutoff_time: "09:50",
  cutoff_timezone: "Europe/London",
  days_before: 1,
  availability_lag_minutes: 0,
  resolution: "half_hour" as const,
  hour_alignment: "start" as const,
  conflict_policy: "exclude" as const,
  top_k: 10,
  histogram_bin_mw: 500,
};

const alignment = { value: "start" as const, status: "assumed" as const, note: "ASSUMPTION (unverified): a WINDFOR row stamped T describes the hour starting at T." };

export function makeSummary(over: Partial<Summary> = {}): Summary {
  return {
    config,
    provenance: provenance(),
    alignment,
    cutoff: {
      description: "Decision cutoff = 09:50 Europe/London on the day 1 day(s) before each delivery date. This is a configurable assumption, not a verified market deadline.",
      first_delivery_date: "2026-01-01",
      first_cutoff_utc: "2025-12-31T09:50:00Z",
      first_cutoff_local: "2025-12-31T09:50:00+00:00",
      status: "configurable_assumption",
    },
    resolution_note: "Hourly forecasts are applied to both half-hours they cover; they are NOT independent half-hour forecasts.",
    counts: counts(),
    counts_by_resolution: { half_hour: counts(), hourly: counts({ expected: 48, matched: 48, actual_observed: 48, forecast_available: 48, unit: "hours" }) },
    metrics: metrics(),
    daily: [
      { delivery_date: "2026-01-01", expected: 48, matched: 48, coverage: 1, metrics: metrics({ n: 48 }) },
      { delivery_date: "2026-01-02", expected: 48, matched: 48, coverage: 1, metrics: metrics({ n: 48, bias: -80 }) },
    ],
    distribution: {
      bin_width_mw: 500,
      bins: [
        { lower_mw: -500, upper_mw: 0, count: 60 },
        { lower_mw: 0, upper_mw: 500, count: 36 },
      ],
      quantiles_mw: { p5: -400, p10: -300, p25: -200, p50: -100, p75: 50, p90: 200, p95: 300 },
      over_forecast_count: 60,
      under_forecast_count: 36,
      exact_count: 0,
      error_definition: "error = actual - forecast; negative = forecast above actual (over-forecast)",
    },
    under_forecasts: [{ start_utc: "2026-01-02T10:00:00Z", start_local: "2026-01-02T10:00:00+00:00", error_mw: 450, actual_mw: 5450, forecast_mw: 5000 }],
    over_forecasts: [{ start_utc: "2026-01-01T03:00:00Z", start_local: "2026-01-01T03:00:00+00:00", error_mw: -480, actual_mw: 4520, forecast_mw: 5000 }],
    elevated_days: ["2026-01-02"],
    lead_time_h: { min: 14.5, median: 26, max: 37.5 },
    vintages_used: 2,
    warnings: [
      { code: "ALIGNMENT_ASSUMED", severity: "info", message: alignment.note },
      { code: "SCOPE_MISMATCH", severity: "warning", message: "FUELHH WIND and WINDFOR may not cover the same generators." },
    ],
    ...over,
  };
}

/** 2 delivery days of half-hours with optional holes. */
export function makeInterval(i: number, over: Partial<Interval> = {}): Interval {
  const start = Date.UTC(2026, 0, 1) + i * 30 * 60_000;
  const iso = (ms: number) => new Date(ms).toISOString().replace(".000Z", "Z");
  const date = iso(start).slice(0, 10);
  const actual = 5000 + (i % 7) * 10;
  const forecast = 5100;
  return {
    start_utc: iso(start),
    end_utc: iso(start + 30 * 60_000),
    start_local: iso(start).replace("Z", "+00:00"),
    delivery_date: date,
    actual_mw: actual,
    forecast_mw: forecast,
    error_mw: actual - forecast,
    status: "MATCHED",
    forecast_published_at: "2025-12-31T09:30:00Z",
    lead_time_h: 14.5 + Math.floor(i / 2),
    forecast_row_start: iso(Math.floor(start / 3_600_000) * 3_600_000),
    cutoff_utc: "2025-12-31T09:50:00Z",
    vintages_total: 5,
    vintages_eligible: 3,
    vintages_after_cutoff: 2,
    unavailable_reason: null,
    conflict_fallback: false,
    conflict_involved: false,
    actual_conflict: false,
    ...over,
  };
}

export function makeIntervals(n = 96, patch: Record<number, Partial<Interval>> = {}): Intervals {
  const intervals = Array.from({ length: n }, (_, i) => makeInterval(i, patch[i]));
  return { config, provenance: provenance(), alignment, resolution_note: "Hourly forecasts are applied to both half-hours they cover; they are NOT independent half-hour forecasts.", counts: counts({ expected: n, matched: intervals.filter((x) => x.status === "MATCHED").length }), intervals };
}

export const UNAVAILABLE: Partial<Interval> = {
  forecast_mw: null,
  error_mw: null,
  status: "FORECAST_UNAVAILABLE",
  forecast_published_at: null,
  lead_time_h: null,
  unavailable_reason: "no_eligible_forecast",
  vintages_eligible: 0,
  vintages_after_cutoff: 3,
};
export const ACTUAL_MISSING: Partial<Interval> = { actual_mw: null, error_mw: null, status: "ACTUAL_MISSING" };
export const ZERO_ACTUAL: Partial<Interval> = { actual_mw: 0, error_mw: -5100 };

export function makeRevisions(over: Partial<Revisions> = {}): Revisions {
  const interval = makeInterval(0);
  return {
    config,
    interval,
    forecast_row_start: interval.forecast_row_start,
    hour_start: interval.forecast_row_start,
    cutoff_utc: "2025-12-31T09:50:00Z",
    vintages: [
      { publish_utc: "2026-01-01T02:30:00Z", forecast_mw: 5300, lead_time_h: -2.5, relative_to_cutoff_min: 997, eligible: false, selected: false, error_if_used_mw: -300, note: "Not usable: published after the delivery hour began (back-cast)." },
      { publish_utc: "2025-12-31T11:30:00Z", forecast_mw: 5200, lead_time_h: 12.5, relative_to_cutoff_min: 100, eligible: false, selected: false, error_if_used_mw: -200, note: "Not available at decision time (published after the cutoff). Shown for context only." },
      { publish_utc: "2025-12-31T09:30:00Z", forecast_mw: 5100, lead_time_h: 14.5, relative_to_cutoff_min: -20, eligible: true, selected: true, error_if_used_mw: -100, note: "Selected: the latest vintage published at or before the cutoff." },
      { publish_utc: "2025-12-31T07:30:00Z", forecast_mw: 5000, lead_time_h: 16.5, relative_to_cutoff_min: -140, eligible: true, selected: false, error_if_used_mw: 0, note: "Eligible at decision time, but superseded by a later eligible vintage." },
    ],
    conflicted_vintages: [],
    explanation: [
      "Delivery date 2026-01-01; decision cutoff 2025-12-31T09:50:00Z (2025-12-31 09:50 Europe/London).",
      "The forecast row consulted is WINDFOR startTime 2026-01-01T00:00:00Z (alignment 'start' is an unverified assumption).",
      "4 vintage(s) exist for that row; 2 were published at or before the cutoff and 2 after it.",
      "Selected the latest eligible vintage, published 2025-12-31T09:30:00Z (14.5 h before the hour began): 5,100 MW.",
    ],
    alignment,
    ...over,
  };
}

export function makeMeta(over: Partial<Meta> = {}): Meta {
  return {
    app_version: "0.1.0",
    purpose: "Retrospective simulation of historical day-ahead decision-making for January 2026 deliveries.",
    permitted_window: { start: "2026-01-01", end: "2026-01-31" },
    defaults: config,
    cutoff_presets: [
      { id: "n2ex_0950", label: "09:50 (provisional default)", time: "09:50", timezone: "Europe/London", status: "configurable_assumption", basis: "Nord Pool page, 2022" },
      { id: "epex_0920", label: "09:20", time: "09:20", timezone: "Europe/London", status: "configurable_assumption", basis: "EPEX snippets" },
      { id: "epex_1530", label: "15:30", time: "15:30", timezone: "Europe/London", status: "configurable_assumption", basis: "EPEX 2018" },
    ],
    resolutions: [{ id: "half_hour", label: "30-minute", note: "" }, { id: "hourly", label: "Native hourly", note: "" }],
    alignment_options: [{ id: "start", label: "Row covers the hour starting at startTime (assumed)", status: "assumed", note: "" }, { id: "end", label: "Row covers the hour ending at startTime (sensitivity)", status: "assumed", note: "" }],
    conflict_policies: [{ id: "exclude", label: "Exclude", note: "" }, { id: "strict", label: "Strict", note: "" }],
    datasets: [
      { id: "FUELHH", role: "Actual generation", description: "Half-hourly outturn.", documentation: "https://example.test/fuelhh", resolution: "30 minutes" },
      { id: "WINDFOR", role: "Forecast generation", description: "Wind forecast.", documentation: "https://example.test/windfor", resolution: "60 minutes" },
    ],
    provenance: provenance(),
    attribution: "Contains BMRS data (c) Elexon Limited copyright and database right.",
    scope_diagnostic: {
      headline: "FUELHH WIND and WINDFOR may not cover the same generators.",
      body: "Fixture scope text.",
      evidence: { fuelhh_minus_b1630_mean_mw: -2249, share_of_half_hours_fuelhh_below_b1630_pct: 99.9, january_bias_vs_fuelhh_mw: -1840, january_bias_vs_b1630_mw: 408, january_mae_vs_fuelhh_mw: 2126, january_mae_vs_b1630_mw: 1338 },
      source: "docs/planning/04-data-research-notes.md",
      measured_on: "2026-10-25",
      not_established: ["Exact asset coverage of each dataset."],
    },
    error_convention: "error = actual generation - forecast generation (MW). Positive: actual exceeded the forecast.",
    ...over,
  };
}

export function makeScenarios(over: Partial<Scenarios> = {}): Scenarios {
  const m = metrics();
  return {
    config,
    provenance: provenance(),
    disclaimer: "Analytical scenario based on historical forecast errors in a single month. It is not a purchase recommendation and does not estimate any shortfall, volume, cost or saving.",
    caveats: ["Based on one winter month.", "In-sample."],
    sample: { matched_intervals: 96, delivery_days: 2, unit: "half-hour" },
    level_offset_mw: -120,
    error_std_mw: 160,
    buffers: [50, 80, 90, 95].map((c, i) => ({ confidence_pct: c, buffer_mw: 100 * (i + 1), raw_quantile_mw: 100 * (i + 1), energy_mwh_per_interval_if_sustained: 50 * (i + 1) })),
    bands: [],
    by_hour_of_day: [{ label: "00:00", metrics: m }, { label: "01:00", metrics: m }],
    by_lead_time: [],
    by_forecast_level: [],
    elevated_days: ["2026-01-02"],
    rolling_origin: [{ confidence_pct: 90, realised_pct: 86.6, evaluated_days: 23, skipped_days: 8, days: [] }],
    interval_unit: "half-hour",
    ...over,
  };
}

export function makeDataQuality(over: Partial<DataQuality> = {}): DataQuality {
  const norm = { input_rows: 10, accepted_rows: 10, rejected_rows: 0, off_grid_rows: 0, null_generation_rows: 0, zero_generation_rows: 0, duplicate_rows_collapsed: 0, conflicting_keys: 0 };
  return {
    config,
    provenance: provenance(),
    sources: [],
    counts: counts(),
    counts_by_resolution: {},
    normalisation: { FUELHH: norm, WINDFOR: { ...norm, input_rows: 20, accepted_rows: 20 } },
    conflicts: [],
    conflict_total: 0,
    vintage_stats: {},
    anomalies: [{ type: "MISSING_VINTAGE", detail: "No forecast published at 11:30Z on 2026-01-15.", date: "2026-01-15" }],
    assumptions: ["Delivery date = Europe/London settlement date."],
    limitations: ["Fixture limitation"],
    scope_diagnostic: makeMeta().scope_diagnostic,
    partial_hour_sps: 0,
    unexpected_actual_rows: 0,
    ...over,
  };
}
