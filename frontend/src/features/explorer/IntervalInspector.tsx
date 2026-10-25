import { ChevronLeft, ChevronRight, Layers } from "lucide-react";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { useRevisions } from "@/api/hooks";
import type { Interval, Revisions, Vintage } from "@/api/types";
import { AsyncPanel } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorWord, fmtHours, fmtLocal, fmtMw, fmtUtc, NA } from "@/lib/format";
import type { AnalysisParams } from "@/lib/params";
import { COLOURS } from "./ForecastChart";

const STATUS_LABEL: Record<Interval["status"], { text: string; tone: "good" | "warn" | "bad" | "neutral" }> = {
  MATCHED: { text: "Matched", tone: "good" },
  FORECAST_UNAVAILABLE: { text: "Forecast unavailable", tone: "warn" },
  ACTUAL_MISSING: { text: "Actual missing", tone: "bad" },
  BOTH_MISSING: { text: "Both missing", tone: "bad" },
};

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/40 py-1.5 text-sm last:border-0">
      <dt className="text-muted">{k}</dt>
      <dd className="text-right tabular-nums text-ink">{children}</dd>
    </div>
  );
}

function VintageBadge({ v }: { v: Vintage }) {
  if (v.selected) return <Badge tone="good">Selected</Badge>;
  if (v.eligible) return <Badge>Eligible · superseded</Badge>;
  if (v.lead_time_h <= 0) return <Badge tone="bad">Back-cast · after the hour began</Badge>;
  if (v.relative_to_cutoff_min > 0) return <Badge tone="warn">After cutoff · not known</Badge>;
  return <Badge tone="bad">Not usable</Badge>;
}

export function VintageTable({ data }: { data: Revisions }) {
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Forecast revisions table">
      <table className="w-full min-w-[34rem] text-left text-xs" data-testid="vintage-table">
        <caption className="sr-only">All forecast vintages targeting this interval, newest first</caption>
        <thead className="text-muted">
          <tr>
            <th scope="col" className="py-1 pr-3 font-medium">Published (London)</th>
            <th scope="col" className="py-1 pr-3 text-right font-medium">Forecast</th>
            <th scope="col" className="py-1 pr-3 text-right font-medium">vs cutoff</th>
            <th scope="col" className="py-1 pr-3 text-right font-medium">Error if used</th>
            <th scope="col" className="py-1 font-medium">Status at decision time</th>
          </tr>
        </thead>
        <tbody>
          {data.vintages.map((v) => (
            <tr key={v.publish_utc} data-selected={v.selected} className={v.selected ? "bg-actual/10" : undefined}>
              <td className="py-1.5 pr-3 tabular-nums">{fmtLocal(v.publish_utc)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{v.forecast_mw === null ? "no value" : fmtMw(v.forecast_mw)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums text-muted">
                {v.relative_to_cutoff_min <= 0 ? `${Math.round(-v.relative_to_cutoff_min)} min before` : `${Math.round(v.relative_to_cutoff_min)} min after`}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{v.error_if_used_mw === null ? NA : fmtMw(v.error_if_used_mw, { signed: true })}</td>
              <td className="py-1.5"><VintageBadge v={v} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RevisionChart({ data }: { data: Revisions }) {
  const pts = [...data.vintages]
    .filter((v) => v.forecast_mw !== null)
    .map((v) => ({ t: Date.parse(v.publish_utc), mw: v.forecast_mw as number, selected: v.selected, eligible: v.eligible }))
    .sort((a, b) => a.t - b.t);
  if (pts.length === 0) return null;
  const cutoff = Date.parse(data.cutoff_utc);
  const actual = data.interval.actual_mw;
  return (
    <div data-testid="revision-chart" role="img" aria-label="How the forecast for this interval changed across publications, with the decision cutoff marked">
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={pts} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={COLOURS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} stroke={COLOURS.axis} tick={{ fontSize: 10 }}
            tickFormatter={(t: number) => new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(t))}
            minTickGap={50} />
          <YAxis stroke={COLOURS.axis} tick={{ fontSize: 10 }} width={44} domain={["auto", "auto"]} tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`} />
          <Tooltip isAnimationActive={false} formatter={(v) => fmtMw(Number(v))} labelFormatter={(t) => fmtLocal(new Date(Number(t)).toISOString())}
            contentStyle={{ background: "#17233b", border: "1px solid #263553", fontSize: 12 }} />
          <ReferenceLine x={cutoff} stroke="#ff8a7a" strokeDasharray="4 3" label={{ value: "decision cutoff", position: "insideTopLeft", fill: "#ff8a7a", fontSize: 10 }} />
          {actual !== null ? <ReferenceLine y={actual} stroke={COLOURS.actual} strokeDasharray="2 2" label={{ value: "actual", position: "insideBottomRight", fill: COLOURS.actual, fontSize: 10 }} /> : null}
          <Line dataKey="mw" name="Forecast" stroke={COLOURS.forecast} type="stepAfter" dot={{ r: 3 }} isAnimationActive={false} />
          <Scatter dataKey="mw" fill="#fff" isAnimationActive={false} shape={(p: { cx?: number; cy?: number; payload?: { selected: boolean } }) =>
            p.payload?.selected ? <circle cx={p.cx} cy={p.cy} r={6} fill="none" stroke="#3dd6c6" strokeWidth={2} /> : <g />} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function IntervalInspector({
  interval,
  params,
  onStep,
  canPrev,
  canNext,
}: {
  interval: Interval | null;
  params: AnalysisParams;
  onStep: (delta: -1 | 1) => void;
  canPrev: boolean;
  canNext: boolean;
}) {
  const rev = useRevisions(interval?.start_utc ?? null, params);
  if (!interval) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted" data-testid="inspector-empty">
        <Layers className="size-5" aria-hidden />
        Select an interval on the chart (or use the arrow keys / buttons) to see what was known at decision time.
      </div>
    );
  }
  const st = STATUS_LABEL[interval.status];
  return (
    <div className="flex flex-col gap-4" data-testid="interval-inspector">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-ink">{fmtLocal(interval.start_local)}</p>
          <p className="text-xs text-muted">{fmtUtc(interval.start_utc)} · {params.resolution === "hourly" ? "1-hour" : "30-minute"} interval</p>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" aria-label="Previous interval" disabled={!canPrev} onClick={() => onStep(-1)}><ChevronLeft className="size-4" aria-hidden /></Button>
          <Button variant="ghost" aria-label="Next interval" disabled={!canNext} onClick={() => onStep(1)}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
      </div>
      <Badge tone={st.tone} className="self-start" data-testid="inspector-status">{st.text}</Badge>
      <dl>
        <Row k="Actual (FUELHH)">{interval.actual_mw === null ? <span className="text-over">missing</span> : fmtMw(interval.actual_mw)}</Row>
        <Row k="Forecast (WINDFOR)">{interval.forecast_mw === null ? <span className="text-warn">unavailable at cutoff</span> : fmtMw(interval.forecast_mw)}</Row>
        <Row k="Error (actual − forecast)">
          {interval.error_mw === null ? NA : (
            <span title={errorWord(interval.error_mw)}>{fmtMw(interval.error_mw, { signed: true })}</span>
          )}
        </Row>
        {interval.error_mw !== null ? <p className="py-1 text-xs text-muted" data-testid="error-sign-note">{errorWord(interval.error_mw)}</p> : null}
        <Row k="Forecast published">{interval.forecast_published_at ? fmtLocal(interval.forecast_published_at) : NA}</Row>
        <Row k="Lead time before the hour">{fmtHours(interval.lead_time_h)}</Row>
        <Row k="Decision cutoff">{fmtLocal(interval.cutoff_utc)}</Row>
        <Row k="Vintages (eligible / after cutoff)">{interval.vintages_eligible} / {interval.vintages_after_cutoff}</Row>
      </dl>
      {params.resolution === "half_hour" && interval.forecast_mw !== null ? (
        <p className="rounded-md bg-raised/60 px-3 py-2 text-xs text-muted">
          This hourly forecast is shared by both half-hours of the hour; it is not an independent half-hour forecast.
        </p>
      ) : null}

      <p className="text-[11px] leading-snug text-muted" data-testid="inspector-scope-note">
        Differences between FUELHH and WINDFOR may reflect dataset scope as well as forecast performance.
      </p>

      <section aria-label="Why this forecast was selected">
        <h3 className="mb-2 text-sm font-semibold text-ink">Why this forecast?</h3>
        <AsyncPanel query={rev} skeletonClassName="h-40" label="Loading revision details">
          {(data) => (
            <div className="flex flex-col gap-3">
              <ol className="list-decimal space-y-1 pl-5 text-[13px] leading-snug text-muted" data-testid="why-selected">
                {data.explanation.map((line) => <li key={line}>{line}</li>)}
              </ol>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Forecast revisions</h4>
              <RevisionChart data={data} />
              <VintageTable data={data} />
              <p className="text-[11px] text-muted">Vintages after the cutoff are shown for context only — they were not available at decision time.</p>
            </div>
          )}
        </AsyncPanel>
      </section>
    </div>
  );
}
