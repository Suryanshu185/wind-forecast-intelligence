import { OctagonAlert } from "lucide-react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useScenarios } from "@/api/hooks";
import type { Scenarios } from "@/api/types";
import { AsyncPanel, EmptyState } from "@/components/states";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { InfoTip } from "@/components/ui/info-tip";
import { fmtDate, fmtInt, fmtMw } from "@/lib/format";
import type { AnalysisParams } from "@/lib/params";

const C = { mae: "#3dd6c6", bias: "#f5b84a", grid: "#263553", axis: "#9aa8c2" };

function Disclaimer({ text }: { text: string }) {
  return (
    <div role="note" data-testid="scenario-disclaimer" className="flex items-start gap-3 rounded-lg border border-warn/50 bg-warn/10 px-4 py-3 text-sm text-ink">
      <OctagonAlert className="mt-0.5 size-5 shrink-0 text-warn" aria-hidden />
      <div>
        <p className="font-semibold">Illustrative analytical scenario — not a purchase or trading recommendation</p>
        <p className="mt-1 text-[13px] text-muted">{text}</p>
      </div>
    </div>
  );
}

function BufferTable({ s }: { s: Scenarios }) {
  return (
    <table className="w-full text-sm" data-testid="buffer-table">
      <caption className="sr-only">Illustrative wind under-delivery buffers from historical errors</caption>
      <thead className="text-left text-xs text-muted">
        <tr>
          <th scope="col" className="py-1.5 pr-3 font-medium">Historical confidence</th>
          <th scope="col" className="py-1.5 pr-3 text-right font-medium">Under-delivery buffer</th>
          <th scope="col" className="hidden py-1.5 pr-3 text-right font-medium sm:table-cell">Equivalent energy if sustained for one interval</th>
          <th scope="col" className="py-1.5 font-medium">Reading</th>
        </tr>
      </thead>
      <tbody>
        {s.buffers.map((b) => (
          <tr key={b.confidence_pct} className="border-t border-border/40 align-top">
            <th scope="row" className="py-2 pr-3 text-left font-medium">{b.confidence_pct}%</th>
            <td className="py-2 pr-3 text-right font-semibold tabular-nums">{fmtMw(b.buffer_mw)}</td>
            <td className="hidden py-2 pr-3 text-right tabular-nums text-muted sm:table-cell">{fmtInt(b.energy_mwh_per_interval_if_sustained)} MWh</td>
            <td className="py-2 text-xs text-muted">
              In {b.confidence_pct}% of matched {s.interval_unit} intervals, wind output was no more than {fmtMw(b.buffer_mw)} below the forecast.
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HourOfDay({ s }: { s: Scenarios }) {
  const data = s.by_hour_of_day.map((b) => ({ hour: b.label, mae: b.metrics.mae, bias: b.metrics.bias, n: b.metrics.n }));
  return (
    <div data-testid="hour-of-day" role="img" aria-label="Mean absolute error and bias by London local hour of day">
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="hour" stroke={C.axis} tick={{ fontSize: 10 }} interval={2} />
          <YAxis stroke={C.axis} tick={{ fontSize: 11 }} width={48} tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`} label={{ value: "MW", angle: -90, position: "insideLeft", fill: C.axis, fontSize: 11 }} />
          <ReferenceLine y={0} stroke={C.axis} />
          <Tooltip isAnimationActive={false} contentStyle={{ background: "#17233b", border: "1px solid #263553", fontSize: 12 }}
            formatter={(v, name) => [fmtMw(typeof v === "number" ? v : null, { signed: name === "Bias" }), name as string]} />
          <Bar dataKey="mae" name="MAE" fill={C.mae} fillOpacity={0.7} isAnimationActive={false} />
          <Line dataKey="bias" name="Bias" stroke={C.bias} strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Rolling({ s }: { s: Scenarios }) {
  if (s.rolling_origin.every((r) => r.evaluated_days === 0)) {
    return <EmptyState title="Not enough history for the out-of-sample check">Needs at least 7 earlier delivery days; widen the date range.</EmptyState>;
  }
  return (
    <table className="w-full text-sm" data-testid="rolling-table">
      <caption className="sr-only">Out-of-sample calibration of the buffers</caption>
      <thead className="text-left text-xs text-muted">
        <tr>
          <th scope="col" className="py-1.5 pr-3 font-medium">Nominal confidence</th>
          <th scope="col" className="py-1.5 pr-3 text-right font-medium">Realised out-of-sample</th>
          <th scope="col" className="py-1.5 text-right font-medium">Days evaluated</th>
        </tr>
      </thead>
      <tbody>
        {s.rolling_origin.map((r) => (
          <tr key={r.confidence_pct} className="border-t border-border/40">
            <th scope="row" className="py-1.5 pr-3 text-left font-medium">{r.confidence_pct}%</th>
            <td className="py-1.5 pr-3 text-right tabular-nums">{r.realised_pct === null ? "—" : `${r.realised_pct.toFixed(1)}%`}</td>
            <td className="py-1.5 text-right tabular-nums text-muted">{r.evaluated_days} <span className="text-xs">({r.skipped_days} skipped)</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DecisionPanel({ params }: { params: AnalysisParams }) {
  const q = useScenarios(params, true);
  return (
    <div className="flex flex-col gap-5" aria-label="Decision intelligence">
      <AsyncPanel query={q} skeletonClassName="h-96" label="Loading scenarios" isEmpty={(s) => s.buffers.length === 0}
        empty={<EmptyState title="No scenarios available">Scenarios need matched intervals; none exist for this selection.</EmptyState>}>
        {(s) => (
          <>
            <Disclaimer text={s.disclaimer} />
            <p className="text-xs text-muted" data-testid="scope-reminder">{s.scope_notice}</p>
            <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
              <Card aria-labelledby="buffers-title">
                <CardHeader id="buffers-title" title="Illustrative uncertainty buffers"
                  subtitle={`Empirical quantiles of historical wind under-delivery (forecast − actual) over ${fmtInt(s.sample.matched_intervals)} matched ${s.interval_unit} intervals across ${s.sample.delivery_days} days.`}
                  actions={<InfoTip label="About these buffers">Buffer at confidence c = c-th percentile of (forecast − actual), floored at 0. It describes the past month only. It is not a recommended purchase volume: demand, contracts, other generation and prices are not in this data.</InfoTip>} />
                <CardBody><BufferTable s={s} /></CardBody>
              </Card>
              <Card aria-labelledby="offset-title">
                <CardHeader id="offset-title" title="Level offset versus variability" subtitle="Why the dataset-scope caveat matters for these buffers." />
                <CardBody className="space-y-3 text-sm">
                  <dl className="grid grid-cols-[1fr_auto] gap-y-1.5">
                    <dt className="text-muted">Mean signed error (level offset)</dt><dd className="text-right font-semibold tabular-nums" data-testid="level-offset">{fmtMw(s.level_offset_mw, { signed: true })}</dd>
                    <dt className="text-muted">Spread around that offset (std)</dt><dd className="text-right font-semibold tabular-nums">{fmtMw(s.error_std_mw)}</dd>
                  </dl>
                  <p className="text-xs text-muted">The buffers above include the offset. Part of it may reflect FUELHH and WINDFOR covering different generators rather than forecast skill, so it is reported separately and no correction is applied.</p>
                </CardBody>
              </Card>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <Card aria-labelledby="hod-title">
                <CardHeader id="hod-title" title="Error by hour of day (London)" subtitle="Where in the day FUELHH and WINDFOR differed most (dataset scope included — not pure forecast skill)." />
                <CardBody><HourOfDay s={s} /></CardBody>
              </Card>
              <Card aria-labelledby="roll-title">
                <CardHeader id="roll-title" title="Out-of-sample check" subtitle="Each day’s buffer uses only earlier days (up to D−2); this is how often reality stayed inside it."
                  actions={<InfoTip label="About the out-of-sample check">For each delivery day D with at least 7 earlier days, the buffer is computed from days up to D−2 only, then compared with what happened on D.</InfoTip>} />
                <CardBody className="space-y-3">
                  <Rolling s={s} />
                  <h3 className="pt-2 text-sm font-semibold">Elevated-error days</h3>
                  {s.elevated_days.length === 0 ? <p className="text-sm text-muted">None flagged.</p> : (
                    <ul className="flex flex-wrap gap-2" data-testid="elevated-days">
                      {s.elevated_days.map((d) => <li key={d} className="rounded-full border border-over/40 bg-over/10 px-2.5 py-0.5 text-xs text-over">{fmtDate(d)}</li>)}
                    </ul>
                  )}
                  <p className="text-xs text-muted">Days in the top quartile of daily RMSE for this period (≥ 80% coverage) — elevated relative to this month, not to any external standard.</p>
                </CardBody>
              </Card>
            </div>

            <Card aria-labelledby="impl-title">
              <CardHeader id="impl-title" title="What this can and cannot tell a procurement team" />
              <CardBody className="grid gap-5 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-actual">It can show</h3>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
                    <li>How far wind output departed from the forecast that was available at the cutoff.</li>
                    <li>Which hours and days carried the largest forecast uncertainty.</li>
                    <li>How sensitive the picture is to the assumed cutoff, lag and resolution.</li>
                  </ul>
                </div>
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-warn">It cannot show</h3>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
                    <li>The utility’s actual shortfall or optimal purchase volume (no demand, contract or other-generation data).</li>
                    <li>Costs, savings or trading profit (no price data).</li>
                    <li>Future accuracy — this is one winter month, evaluated in-sample.</li>
                  </ul>
                </div>
              </CardBody>
            </Card>

            <Card aria-labelledby="cav-title">
              <CardHeader id="cav-title" title="Caveats" />
              <CardBody><ul className="list-disc space-y-1 pl-5 text-sm text-muted">{s.caveats.map((c) => <li key={c}>{c}</li>)}</ul></CardBody>
            </Card>
          </>
        )}
      </AsyncPanel>
    </div>
  );
}
