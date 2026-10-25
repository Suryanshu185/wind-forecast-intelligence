import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useDataQuality, useMeta } from "@/api/hooks";
import type { DataQuality, Meta } from "@/api/types";
import { ProvenanceBadge } from "@/components/banners";
import { AsyncPanel } from "@/components/states";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { fmtInt, fmtMw, fmtRetrieved } from "@/lib/format";
import { useAnalysisParams } from "@/lib/use-params";
import { CoverageBreakdown } from "../accuracy/MetricsGrid";

const FORMULAS: Array<[string, string, string]> = [
  ["Signed error", "e = actual − forecast", "Positive: actual above forecast (under-forecast). Negative: actual below forecast (over-forecast)."],
  ["MAE", "mean(|e|)", "Mean absolute error in MW."],
  ["RMSE", "√ mean(e²)", "Penalises large errors; RMSE ≥ MAE."],
  ["Bias", "mean(e)", "Mean signed error; negative means the forecast was on average above actual."],
  ["P90 absolute error", "90th percentile of |e| (linear interpolation)", "Nine in ten matched intervals had an error no larger than this."],
  ["Error spread", "√ mean((e − ē)²)", "RMSE² = bias² + spread². Separates a level offset from variability."],
  ["Coverage", "matched ÷ expected", "Expected intervals come from the calendar (48 per normal day), not from the data."],
];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card id={id} aria-labelledby={`${id}-t`} className="scroll-mt-24">
      <CardHeader id={`${id}-t`} title={title} />
      <CardBody className="space-y-3 text-sm leading-relaxed text-muted">{children}</CardBody>
    </Card>
  );
}

function Scope({ meta }: { meta: Meta }) {
  const s = meta.scope_diagnostic;
  const e = s.evidence;
  return (
    <Section id="scope" title="Dataset scope: FUELHH WIND versus WINDFOR">
      <p className="font-medium text-ink">{s.headline}</p>
      <p>{s.body}</p>
      <table className="w-full max-w-xl text-sm" data-testid="scope-evidence">
        <caption className="sr-only">Diagnostic evidence (static research finding)</caption>
        <tbody>
          <tr className="border-t border-border/40"><th scope="row" className="py-1.5 pr-3 text-left font-normal">FUELHH WIND minus B1630 wind, mean</th><td className="text-right tabular-nums text-ink">{fmtMw(e.fuelhh_minus_b1630_mean_mw, { signed: true })}</td></tr>
          <tr className="border-t border-border/40"><th scope="row" className="py-1.5 pr-3 text-left font-normal">January bias of this forecast versus FUELHH</th><td className="text-right tabular-nums text-ink">{fmtMw(e.january_bias_vs_fuelhh_mw, { signed: true })}</td></tr>
          <tr className="border-t border-border/40"><th scope="row" className="py-1.5 pr-3 text-left font-normal">…versus B1630 (diagnostic only)</th><td className="text-right tabular-nums text-ink">{fmtMw(e.january_bias_vs_b1630_mw, { signed: true })}</td></tr>
          <tr className="border-t border-border/40"><th scope="row" className="py-1.5 pr-3 text-left font-normal">January MAE versus FUELHH / B1630</th><td className="text-right tabular-nums text-ink">{fmtMw(e.january_mae_vs_fuelhh_mw)} / {fmtMw(e.january_mae_vs_b1630_mw)}</td></tr>
        </tbody>
      </table>
      <p className="text-xs">{s.measured_on}. Source: <code>{s.source}</code>. B1630 is used here only as a diagnostic cross-reference and is not part of the analysis.</p>
      <p className="mt-2 font-medium text-ink">Not established</p>
      <ul className="list-disc pl-5">{s.not_established.map((x) => <li key={x}>{x}</li>)}</ul>
    </Section>
  );
}

function Quality({ dq }: { dq: DataQuality }) {
  const fh = dq.normalisation.FUELHH ?? {};
  const wf = dq.normalisation.WINDFOR ?? {};
  const rows: Array<[string, unknown, unknown]> = [
    ["Rows read", fh.input_rows, wf.input_rows],
    ["Rows accepted", fh.accepted_rows, wf.accepted_rows],
    ["Rejected (invalid)", fh.rejected_rows, wf.rejected_rows],
    ["Off-grid timestamps excluded", fh.off_grid_rows, wf.off_grid_rows],
    ["Null generation (missing)", fh.null_generation_rows, wf.null_generation_rows],
    ["Zero generation (valid values)", fh.zero_generation_rows, wf.zero_generation_rows],
    ["Exact duplicates collapsed", fh.duplicate_rows_collapsed, wf.duplicate_rows_collapsed],
    ["Conflicting keys (removed, preserved)", fh.conflicting_keys, wf.conflicting_keys],
  ];
  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">Interval accounting</h3>
        <CoverageBreakdown counts={dq.counts} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">Normalisation counters</h3>
        <table className="w-full text-sm" data-testid="normalisation-table">
          <thead className="text-left text-xs text-muted"><tr><th scope="col" className="py-1 font-medium">Check</th><th scope="col" className="py-1 text-right font-medium">FUELHH</th><th scope="col" className="py-1 text-right font-medium">WINDFOR</th></tr></thead>
          <tbody>
            {rows.map(([k, a, b]) => (
              <tr key={k} className="border-t border-border/40"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{k}</th><td className="py-1.5 text-right tabular-nums text-ink">{fmtInt(Number(a))}</td><td className="py-1.5 text-right tabular-nums text-ink">{fmtInt(Number(b))}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs">Conflicting duplicate records are never silently resolved: {dq.conflict_total === 0 ? "none exist in this dataset." : `${dq.conflict_total} key(s) are listed below and excluded.`}</p>
        {dq.conflicts.length > 0 ? (
          <ul className="mt-2 list-disc pl-5 text-xs" data-testid="conflict-list">
            {dq.conflicts.map((c, i) => <li key={i}>{String(c.dataset)} {String(c.start_utc)} {c.publish_utc ? `(published ${String(c.publish_utc)})` : ""}: values {JSON.stringify(c.values_mw)}</li>)}
          </ul>
        ) : null}
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">Observed anomalies in the source data</h3>
        {dq.anomalies.length === 0 ? <p className="text-sm">None detected.</p> : (
          <ul className="list-disc space-y-1 pl-5 text-sm" data-testid="anomaly-list">
            {dq.anomalies.map((a, i) => <li key={i}><span className="font-medium text-ink">{a.type.replaceAll("_", " ").toLowerCase()}</span> — {a.detail}</li>)}
          </ul>
        )}
        <p className="mt-2 text-xs">Anomalies are derived from the data itself; the nominal publication schedule is never assumed.</p>
      </div>
    </div>
  );
}

export function MethodologyPage() {
  const [params] = useAnalysisParams();
  const meta = useMeta();
  const dq = useDataQuality(params);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Data &amp; methodology</h1>
        <p className="mt-1 text-sm text-muted">How the numbers are produced, what they are based on, and where they can mislead. <Link to="/" className="underline decoration-dotted underline-offset-2 hover:text-actual">Back to the dashboard</Link></p>
      </div>

      <AsyncPanel query={meta} skeletonClassName="h-40" label="Loading methodology">
        {(m) => (
          <>
            <Section id="purpose" title="What this is">
              <p>{m.purpose}</p>
              <p>{m.error_convention}</p>
              <ProvenanceBadge provenance={m.provenance} />
            </Section>

            <Section id="selection" title="Which forecast counts as “known at decision time”?">
              <ol className="list-decimal space-y-1 pl-5">
                <li>Each delivery interval has a decision cutoff: a clock time (default 09:50 Europe/London) on the day before delivery (configurable).</li>
                <li>Only WINDFOR forecasts targeting that interval and with <code>publishTime</code> at or before the cutoff (minus any availability lag) are eligible. Forecasts published later are excluded even if they are more accurate.</li>
                <li>The latest eligible forecast is selected. If none exists the interval is <strong className="text-ink">unavailable</strong> — never zero.</li>
                <li>The forecast is matched to the actual by delivery interval, not by publication time.</li>
                <li>Duplicate records with different values are removed, counted and listed — never silently resolved.</li>
              </ol>
              <p>Cutoff presets: {m.cutoff_presets.map((p) => `${p.time} (${p.basis})`).join(" · ")}. They are <strong className="text-ink">configurable assumptions, not verified market deadlines</strong>.</p>
            </Section>

            <Section id="alignment" title="Hourly forecast versus half-hourly actuals">
              <p>WINDFOR is hourly; FUELHH is half-hourly. In the 30-minute view each hourly forecast is applied to both half-hours it covers — it is not an independent half-hour forecast, and errors in adjacent half-hours are dependent. The native hourly view compares the mean of the two half-hours with the forecast.</p>
              <p><strong className="text-ink">Unverified assumption:</strong> {m.alignment_options[0]?.label}. No official source states which hour a WINDFOR row describes; an alternative reading is available as a sensitivity switch and the default is not chosen on error statistics.</p>
            </Section>

            <Section id="metrics" title="Metric definitions">
              <table className="w-full text-sm" data-testid="formula-table">
                <thead className="text-left text-xs"><tr><th scope="col" className="py-1 font-medium">Metric</th><th scope="col" className="py-1 font-medium">Formula</th><th scope="col" className="py-1 font-medium">Notes</th></tr></thead>
                <tbody>
                  {FORMULAS.map(([a, b, c]) => <tr key={a} className="border-t border-border/40 align-top"><th scope="row" className="py-1.5 pr-3 text-left font-medium text-ink">{a}</th><td className="py-1.5 pr-3 font-mono text-xs text-ink">{b}</td><td className="py-1.5">{c}</td></tr>)}
                </tbody>
              </table>
              <p>Units are MW (average power over the interval). Metrics use matched intervals only; no missing value is replaced by zero or interpolated.</p>
            </Section>

            <Scope meta={m} />

            <Section id="sources" title="Source datasets">
              <ul className="space-y-2">
                {m.datasets.map((d) => (
                  <li key={d.id}>
                    <span className="font-medium text-ink">{d.id}</span> — {d.role}, {d.resolution}. {d.description}{" "}
                    <a className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-2 hover:text-actual" href={d.documentation} target="_blank" rel="noreferrer">Official documentation <ExternalLink className="size-3" aria-hidden /></a>
                  </li>
                ))}
              </ul>
              <p>Snapshot retrieved {fmtRetrieved(m.provenance.retrieved_at)}; integrity hash <code className="break-all text-xs">{m.provenance.data_sha256}</code>. Period covered: {Object.entries(m.provenance.period_covered).map(([k, v]) => `${k.replaceAll("_", " ")} ${v}`).join("; ")}.</p>
              <p className="text-xs">Attribution wording used: “{m.attribution}”. <strong className="text-ink">{m.attribution_status}</strong> Third-party data are subject to Elexon’s licence terms and are not covered by this project’s MIT licence.</p>
            </Section>
          </>
        )}
      </AsyncPanel>

      <Section id="quality" title="Data quality for the current selection">
        <AsyncPanel query={dq} skeletonClassName="h-72" label="Loading data quality">
          {(d) => (
            <div className="space-y-5">
              <Quality dq={d} />
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink">Assumptions</h3>
                <ul className="list-disc space-y-1 pl-5" data-testid="assumption-list">{d.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink">Known limitations</h3>
                <ul className="list-disc space-y-1 pl-5" data-testid="limitation-list">{d.limitations.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
            </div>
          )}
        </AsyncPanel>
      </Section>
    </div>
  );
}
