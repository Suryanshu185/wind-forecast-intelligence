import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSummary } from "@/api/hooks";
import type { Extreme, Summary } from "@/api/types";
import { AsyncPanel, EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { InfoTip } from "@/components/ui/info-tip";
import { fmtDate, fmtInt, fmtLocal, fmtMw, fmtPct } from "@/lib/format";
import type { AnalysisParams } from "@/lib/params";
import { CoverageBreakdown, LeadTimeNote, MetricsGrid } from "./MetricsGrid";

const C = { mae: "#3dd6c6", bias: "#f5b84a", over: "#ff8a7a", under: "#7cc4ff", grid: "#263553", axis: "#9aa8c2" };
const tipStyle = { background: "#17233b", border: "1px solid #263553", borderRadius: 6, fontSize: 12 };

function DailyTrend({ summary }: { summary: Summary }) {
  const data = summary.daily.map((d) => ({
    date: d.delivery_date,
    label: fmtDate(d.delivery_date),
    mae: d.metrics.mae,
    bias: d.metrics.bias,
    coverage: d.coverage,
    matched: d.matched,
    expected: d.expected,
  }));
  return (
    <div data-testid="daily-trend" role="img" aria-label="Daily mean absolute error and bias in MW for each delivery date">
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" stroke={C.axis} tick={{ fontSize: 10 }} interval="preserveStartEnd" minTickGap={24} />
          <YAxis stroke={C.axis} tick={{ fontSize: 11 }} width={48} tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`} label={{ value: "MW", angle: -90, position: "insideLeft", fill: C.axis, fontSize: 11 }} />
          <ReferenceLine y={0} stroke={C.axis} />
          <Tooltip
            contentStyle={tipStyle}
            isAnimationActive={false}
            formatter={(v, name) => [fmtMw(typeof v === "number" ? v : null, { signed: name === "Bias" }), name as string]}
            labelFormatter={(l, p) => {
              const row = p?.[0]?.payload as { matched: number; expected: number; coverage: number | null } | undefined;
              return `${l} · ${row?.matched ?? 0}/${row?.expected ?? 0} intervals matched (${fmtPct(row?.coverage)})`;
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="mae" name="MAE" fill={C.mae} fillOpacity={0.75} isAnimationActive={false} />
          <Line dataKey="bias" name="Bias" stroke={C.bias} strokeWidth={2} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Histogram({ summary }: { summary: Summary }) {
  const d = summary.distribution;
  const data = d.bins.map((b) => ({ label: `${b.lower_mw}`, lower: b.lower_mw, upper: b.upper_mw, count: b.count }));
  return (
    <div>
      <div data-testid="error-histogram" role="img" aria-label="Histogram of forecast errors (actual minus forecast) in MW">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: 0 }}>
            <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="lower" stroke={C.axis} tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${v / 1000}k`} interval="preserveStartEnd" minTickGap={14}
              label={{ value: "Error = actual − forecast (MW)  ←  over-forecast | under-forecast  →", position: "insideBottom", offset: -12, fill: C.axis, fontSize: 11 }} />
            <YAxis stroke={C.axis} tick={{ fontSize: 11 }} width={40} label={{ value: "Intervals", angle: -90, position: "insideLeft", fill: C.axis, fontSize: 11 }} />
            <Tooltip contentStyle={tipStyle} isAnimationActive={false}
              labelFormatter={(_, p) => { const r = p?.[0]?.payload as { lower: number; upper: number } | undefined; return r ? `${fmtMw(r.lower, { signed: true, unit: false })} to ${fmtMw(r.upper, { signed: true })}` : ""; }}
              formatter={(v) => [fmtInt(Number(v)), "Intervals"]} />
            <ReferenceLine x={0} stroke={C.axis} />
            <Bar dataKey="count" isAnimationActive={false}>
              {data.map((b) => <Cell key={b.lower} fill={b.upper <= 0 ? C.over : C.under} fillOpacity={0.8} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted" data-testid="distribution-facts">
        <div><dt className="inline">Over-forecast (actual below forecast): </dt><dd className="inline font-medium text-over">{fmtInt(d.over_forecast_count)}</dd></div>
        <div><dt className="inline">Under-forecast (actual above forecast): </dt><dd className="inline font-medium text-under">{fmtInt(d.under_forecast_count)}</dd></div>
        {d.quantiles_mw ? (
          <div><dt className="inline">Error P5 / P50 / P95: </dt><dd className="inline font-medium text-ink">{fmtMw(d.quantiles_mw.p5, { signed: true, unit: false })} / {fmtMw(d.quantiles_mw.p50, { signed: true, unit: false })} / {fmtMw(d.quantiles_mw.p95, { signed: true })}</dd></div>
        ) : null}
      </dl>
    </div>
  );
}

function ExtremesTable({ title, rows, onInspect, tone }: { title: string; rows: Extreme[]; onInspect: (s: string) => void; tone: "over" | "under" }) {
  return (
    <div>
      <h3 className={`mb-2 text-sm font-semibold ${tone === "over" ? "text-over" : "text-under"}`}>{title}</h3>
      {rows.length === 0 ? <p className="text-sm text-muted">None in this selection.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[24rem] text-xs" data-testid={`extremes-${tone}`}>
            <caption className="sr-only">{title}</caption>
            <thead className="text-left text-muted">
              <tr><th scope="col" className="py-1 pr-2 font-medium">Interval (London)</th><th scope="col" className="py-1 pr-2 text-right font-medium">Error</th><th scope="col" className="py-1 pr-2 text-right font-medium">Actual</th><th scope="col" className="py-1 text-right font-medium">Forecast</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.start_utc} className="border-t border-border/40">
                  <td className="py-1 pr-2"><button type="button" className="underline-offset-2 hover:underline" onClick={() => onInspect(r.start_utc)} aria-label={`Inspect interval ${fmtLocal(r.start_utc)}`}>{fmtLocal(r.start_utc)}</button></td>
                  <td className="py-1 pr-2 text-right font-medium tabular-nums">{fmtMw(r.error_mw, { signed: true, unit: false })}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">{fmtMw(r.actual_mw, { unit: false })}</td>
                  <td className="py-1 text-right tabular-nums">{fmtMw(r.forecast_mw, { unit: false })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AccuracyPanel({ params, onInspect }: { params: AnalysisParams; onInspect: (startUtc: string) => void }) {
  const q = useSummary(params);
  return (
    <div className="flex flex-col gap-5" aria-label="Forecast accuracy analytics">
      <AsyncPanel query={q} skeletonClassName="h-96" label="Loading accuracy analytics">
        {(s) => (
          <>
            <Card aria-labelledby="metrics-title">
              <CardHeader id="metrics-title" title="Accuracy metrics" subtitle={<>error = actual − forecast, in MW · {s.cutoff.description}</>}
                actions={<Badge tone={s.counts.coverage_level === "ok" ? "good" : "warn"}>{fmtPct(s.counts.coverage)} coverage</Badge>} />
              <CardBody className="space-y-4">
                <MetricsGrid metrics={s.metrics} counts={s.counts} />
                <p className="text-xs text-muted">{s.resolution_note} <LeadTimeNote summary={s} /></p>
                <p className="text-xs text-warn" data-testid="scope-reminder">{s.scope_notice}</p>
              </CardBody>
            </Card>

            <div className="grid gap-5 lg:grid-cols-[2fr_3fr]">
              <Card aria-labelledby="coverage-title">
                <CardHeader id="coverage-title" title="Coverage, missing and unmatched intervals" subtitle="Nothing is silently excluded or replaced by zero." />
                <CardBody><CoverageBreakdown counts={s.counts} /></CardBody>
              </Card>
              <Card aria-labelledby="daily-title">
                <CardHeader id="daily-title" title="Daily accuracy trend" subtitle="MAE (bars) and bias (line) per delivery date; hover for that day’s coverage." />
                <CardBody><DailyTrend summary={s} /></CardBody>
              </Card>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <Card aria-labelledby="dist-title">
                <CardHeader id="dist-title" title="Forecast error distribution" subtitle="Negative = forecast above actual (over-forecast); positive = actual above forecast."
                  actions={<InfoTip label="About the error distribution">500 MW bins anchored at multiples of 500 MW, half-open [lower, upper). Counts are matched intervals.</InfoTip>} />
                <CardBody>{s.distribution.bins.length === 0 ? <EmptyState title="No matched intervals">There is nothing to plot because no interval has both an actual and an eligible forecast.</EmptyState> : <Histogram summary={s} />}</CardBody>
              </Card>
              <Card aria-labelledby="extremes-title">
                <CardHeader id="extremes-title" title="Largest forecast misses" subtitle="Largest signed differences between FUELHH and WINDFOR. Select one to inspect what was known at decision time." />
                <CardBody className="space-y-5">
                  <ExtremesTable title="Largest over-forecasts (forecast far above actual)" rows={s.over_forecasts} onInspect={onInspect} tone="over" />
                  <ExtremesTable title="Largest under-forecasts (actual far above forecast)" rows={s.under_forecasts} onInspect={onInspect} tone="under" />
                </CardBody>
              </Card>
            </div>
          </>
        )}
      </AsyncPanel>
    </div>
  );
}
