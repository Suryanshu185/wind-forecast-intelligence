/** Presentation helpers. Missing values are NEVER rendered as zero. */

export const NA = "—";

const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function fmtMw(v: number | null | undefined, opts: { signed?: boolean; unit?: boolean } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return NA;
  const n = Math.round(v);
  const body = nf0.format(Math.abs(n));
  const sign = n < 0 ? "−" : opts.signed && n > 0 ? "+" : "";
  return `${sign}${body}${opts.unit === false ? "" : " MW"}`;
}

export function fmtInt(v: number | null | undefined): string {
  return v === null || v === undefined ? NA : nf0.format(v);
}

export function fmtPct(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined) return NA;
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function fmtHours(h: number | null | undefined): string {
  return h === null || h === undefined ? NA : `${nf1.format(h)} h`;
}

const LONDON = "Europe/London";
const dtf = new Intl.DateTimeFormat("en-GB", {
  timeZone: LONDON,
  weekday: "short",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dtfShort = new Intl.DateTimeFormat("en-GB", { timeZone: LONDON, day: "2-digit", month: "short" });
const tfm = new Intl.DateTimeFormat("en-GB", { timeZone: LONDON, hour: "2-digit", minute: "2-digit", hour12: false });
const dtfUtc = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** e.g. "Sat, 10 Jan, 09:30" in Europe/London. */
export const fmtLocal = (iso: string | null | undefined): string => (iso ? dtf.format(new Date(iso)) : NA);
export const fmtLocalTime = (iso: string): string => tfm.format(new Date(iso));
export const fmtUtc = (iso: string | null | undefined): string => (iso ? `${dtfUtc.format(new Date(iso))} UTC` : NA);

/** "2026-01-10" -> "10 Jan" (date-only strings are calendar dates, not instants). */
export function fmtDate(isoDate: string): string {
  return dtfShort.format(new Date(`${isoDate}T12:00:00Z`));
}

export const fmtDateLong = (isoDate: string): string =>
  new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "long", year: "numeric" }).format(
    new Date(`${isoDate}T12:00:00Z`),
  );

export const fmtRetrieved = (iso: string): string =>
  new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" }).format(new Date(iso)) + " UTC";

export function errorWord(e: number): string {
  if (e > 0) return "actual above forecast (under-forecast)";
  if (e < 0) return "actual below forecast (over-forecast)";
  return "forecast matched actual exactly";
}
