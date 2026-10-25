import type { Counts, Metrics, Summary } from "@/api/types";
import { InfoTip } from "@/components/ui/info-tip";
import { cn } from "@/lib/cn";
import { fmtInt, fmtMw, fmtPct, NA } from "@/lib/format";

function MetricCard({
  label,
  tip,
  value,
  sub,
  tone,
  testId,
}: {
  label: string;
  tip: string;
  value: string;
  sub: string;
  tone?: "neutral" | "over" | "under";
  testId: string;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-bg/50 p-4" data-testid={testId}>
      <div className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted">
        {label}
        <InfoTip label={`Definition of ${label}`}>{tip}</InfoTip>
      </div>
      <p className={cn("mt-2 text-2xl font-semibold tabular-nums tracking-tight", tone === "over" && "text-over", tone === "under" && "text-under")} data-testid={`${testId}-value`}>
        {value}
      </p>
      <p className="mt-1 text-xs leading-snug text-muted">{sub}</p>
    </div>
  );
}

export function MetricsGrid({ metrics, counts }: { metrics: Metrics; counts: Counts }) {
  const denom = `over ${fmtInt(metrics.n)} matched of ${fmtInt(counts.expected)} expected ${counts.unit}`;
  const none = metrics.n === 0;
  const biasTone = metrics.bias === null ? "neutral" : metrics.bias < 0 ? "over" : metrics.bias > 0 ? "under" : "neutral";
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <MetricCard
        testId="metric-mae"
        label="MAE"
        tip="Mean Absolute Error = average of |actual − forecast|, in MW. Treats over- and under-forecasts alike."
        value={fmtMw(metrics.mae)}
        sub={none ? "No matched intervals — not computed (not zero)." : `Mean of |error| ${denom}.`}
      />
      <MetricCard
        testId="metric-rmse"
        label="RMSE"
        tip="Root Mean Squared Error = √(average of error²), in MW. Always ≥ MAE; larger when a few errors are very large."
        value={fmtMw(metrics.rmse)}
        sub={none ? "No matched intervals — not computed." : `√ mean of error² ${denom}.`}
      />
      <MetricCard
        testId="metric-bias"
        label="Bias (mean signed error)"
        tone={biasTone}
        tip="Average of (actual − forecast), in MW. Negative = the forecast was on average above actual generation (over-forecast); positive = actual exceeded the forecast. Read together with the dataset-scope caveat."
        value={fmtMw(metrics.bias, { signed: true })}
        sub={
          none
            ? "No matched intervals — not computed."
            : `${metrics.bias !== null && metrics.bias < 0 ? "Forecast above actual on average" : metrics.bias !== null && metrics.bias > 0 ? "Actual above forecast on average" : "No net bias"} · ${denom}.`
        }
      />
      <MetricCard
        testId="metric-p90"
        label="P90 absolute error"
        tip="90th percentile of |actual − forecast| using linear interpolation: 9 in 10 matched intervals had an error no larger than this."
        value={fmtMw(metrics.p90_abs_error)}
        sub={none ? "No matched intervals — not computed." : `90% of |error| values are at or below this ${denom}.`}
      />
      <MetricCard
        testId="metric-std"
        label="Error spread (std)"
        tip="Standard deviation of the signed error = RMSE with the bias removed (RMSE² = bias² + std²). Separates a constant level offset from variability."
        value={fmtMw(metrics.error_std)}
        sub={none ? "No matched intervals — not computed." : "Variability of the error around its own mean. Descriptive only — no bias correction is applied."}
      />
      <MetricCard
        testId="metric-coverage"
        label="Interval coverage"
        tip="Matched intervals ÷ expected intervals. Expected comes from the calendar (48 half-hours per normal day), not from the data. Metrics use matched intervals only; nothing is filled with zero."
        value={fmtPct(counts.coverage)}
        sub={`${fmtInt(counts.matched)} matched ÷ ${fmtInt(counts.expected)} expected ${counts.unit}.`}
        tone={counts.coverage_level === "ok" ? "neutral" : "over"}
      />
    </div>
  );
}

export function CoverageBreakdown({ counts }: { counts: Counts }) {
  const rows: Array<[string, number, string]> = [
    ["Expected", counts.expected, `calendar-based (${counts.unit})`],
    ["Actual observed", counts.actual_observed, "FUELHH value present"],
    ["Forecast available", counts.forecast_available, "an eligible vintage existed at the cutoff"],
    ["Matched", counts.matched, "actual and forecast both present — used in metrics"],
    ["Forecast unavailable", counts.forecast_unavailable, "actual present; no forecast published by the cutoff"],
    ["Actual missing", counts.actual_missing, "forecast present; FUELHH value missing"],
    ["Both missing", counts.both_missing, "neither available"],
    ["Touched by conflicting records", counts.conflict_affected, "see data quality"],
  ];
  return (
    <table className="w-full text-sm" data-testid="coverage-breakdown">
      <caption className="sr-only">Expected, observed, matched and missing interval counts</caption>
      <tbody>
        {rows.map(([k, v, d]) => (
          <tr key={k} className="border-b border-border/40 last:border-0">
            <th scope="row" className="py-1.5 pr-3 text-left font-normal text-ink">{k}</th>
            <td className="py-1.5 pr-3 text-right font-medium tabular-nums">{fmtInt(v)}</td>
            <td className="hidden py-1.5 text-xs text-muted sm:table-cell">{d}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LeadTimeNote({ summary }: { summary: Summary }) {
  const l = summary.lead_time_h;
  if (!l) return <span>{NA}</span>;
  return (
    <span>
      Selected forecasts were published {l.min?.toFixed(1)}–{l.max?.toFixed(1)} h (median {l.median?.toFixed(1)} h) before the hour they describe,
      drawn from {summary.vintages_used} distinct publications.
    </span>
  );
}
