/** Analysis parameters: single source of truth lives in the URL (shareable, back-button friendly). */
import type { Alignment, ConflictPolicy, Resolution } from "@/api/types";

/** Product scope: delivery dates are restricted to January 2026. */
export const WINDOW_START = "2026-01-01";
export const WINDOW_END = "2026-01-31";

export interface AnalysisParams {
  delivery_start: string;
  delivery_end: string;
  cutoff_time: string; // HH:MM, Europe/London
  days_before: number;
  availability_lag_minutes: number;
  resolution: Resolution;
  hour_alignment: Alignment;
  conflict_policy: ConflictPolicy;
}

export const DEFAULT_PARAMS: AnalysisParams = {
  delivery_start: WINDOW_START,
  delivery_end: WINDOW_END,
  cutoff_time: "09:50",
  days_before: 1,
  availability_lag_minutes: 0,
  resolution: "half_hour",
  hour_alignment: "start",
  conflict_policy: "exclude",
};

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export function isValidDate(value: string): boolean {
  if (!DATE_RE.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
}

/** Clamp a date string into the permitted January 2026 window; invalid input falls back to `fallback`. */
export function clampDate(value: string | null | undefined, fallback: string): string {
  if (!value || !isValidDate(value)) return fallback;
  if (value < WINDOW_START) return WINDOW_START;
  if (value > WINDOW_END) return WINDOW_END;
  return value;
}

function intIn(value: string | null, lo: number, hi: number, fallback: number): number {
  if (value === null || value.trim() === "") return fallback;
  const n = Number(value);
  return Number.isInteger(n) && n >= lo && n <= hi ? n : fallback;
}

/** Parse + sanitise URL search params. Never throws; out-of-range values are corrected, not trusted. */
export function parseParams(sp: URLSearchParams): AnalysisParams {
  let start = clampDate(sp.get("from"), DEFAULT_PARAMS.delivery_start);
  let end = clampDate(sp.get("to"), DEFAULT_PARAMS.delivery_end);
  if (start > end) [start, end] = [end, start];
  const cutoff = sp.get("cutoff");
  const res = sp.get("res");
  const align = sp.get("align");
  const policy = sp.get("conflicts");
  return {
    delivery_start: start,
    delivery_end: end,
    cutoff_time: cutoff && TIME_RE.test(cutoff) ? cutoff : DEFAULT_PARAMS.cutoff_time,
    days_before: intIn(sp.get("daysBefore"), 0, 3, DEFAULT_PARAMS.days_before),
    availability_lag_minutes: intIn(sp.get("lag"), 0, 720, DEFAULT_PARAMS.availability_lag_minutes),
    resolution: res === "hourly" ? "hourly" : "half_hour",
    hour_alignment: align === "end" ? "end" : "start",
    conflict_policy: policy === "strict" ? "strict" : "exclude",
  };
}

/** Serialise only non-default values so URLs stay short and readable. */
export function toSearchParams(p: AnalysisParams): URLSearchParams {
  const sp = new URLSearchParams();
  if (p.delivery_start !== DEFAULT_PARAMS.delivery_start) sp.set("from", p.delivery_start);
  if (p.delivery_end !== DEFAULT_PARAMS.delivery_end) sp.set("to", p.delivery_end);
  if (p.cutoff_time !== DEFAULT_PARAMS.cutoff_time) sp.set("cutoff", p.cutoff_time);
  if (p.days_before !== DEFAULT_PARAMS.days_before) sp.set("daysBefore", String(p.days_before));
  if (p.availability_lag_minutes !== DEFAULT_PARAMS.availability_lag_minutes)
    sp.set("lag", String(p.availability_lag_minutes));
  if (p.resolution !== DEFAULT_PARAMS.resolution) sp.set("res", p.resolution);
  if (p.hour_alignment !== DEFAULT_PARAMS.hour_alignment) sp.set("align", p.hour_alignment);
  if (p.conflict_policy !== DEFAULT_PARAMS.conflict_policy) sp.set("conflicts", p.conflict_policy);
  return sp;
}

/** Query string sent to the API (always explicit, so the response echo is unambiguous). */
export function toApiQuery(p: AnalysisParams, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams({
    delivery_start: p.delivery_start,
    delivery_end: p.delivery_end,
    cutoff_time: p.cutoff_time,
    days_before: String(p.days_before),
    availability_lag_minutes: String(p.availability_lag_minutes),
    resolution: p.resolution,
    hour_alignment: p.hour_alignment,
    conflict_policy: p.conflict_policy,
    ...extra,
  });
  return q.toString();
}
