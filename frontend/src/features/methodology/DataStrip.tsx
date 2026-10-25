import { Database } from "lucide-react";
import type { Summary } from "@/api/types";
import { fmtDate, fmtInt, fmtRetrieved, fmtPct } from "@/lib/format";

/** Compact always-visible disclosure of what the numbers are based on. */
export function DataStrip({ summary }: { summary: Summary }) {
  const c = summary.counts;
  const cfg = summary.config;
  const items: Array<[string, string]> = [
    ["Sources", "Elexon FUELHH · WINDFOR"],
    ["Delivery dates", `${fmtDate(cfg.delivery_start)} – ${fmtDate(cfg.delivery_end)} 2026`],
    ["Decision cutoff", `${cfg.cutoff_time} ${cfg.cutoff_timezone}, D−${cfg.days_before}${cfg.availability_lag_minutes ? ` (−${cfg.availability_lag_minutes} min lag)` : ""}`],
    ["Expected", `${fmtInt(c.expected)} ${c.unit}`],
    ["Observed actuals", fmtInt(c.actual_observed)],
    ["Forecast available", fmtInt(c.forecast_available)],
    ["Matched", `${fmtInt(c.matched)} (${fmtPct(c.coverage)})`],
    ["Missing / unmatched", fmtInt(c.expected - c.matched)],
    ["Data retrieved", fmtRetrieved(summary.provenance.retrieved_at)],
  ];
  return (
    <section aria-label="Data basis" data-testid="data-strip" className="rounded-xl border border-border bg-surface/60 px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
        <Database className="size-3.5" aria-hidden /> Data basis
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-5">
        {items.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-[11px] text-muted">{k}</dt>
            <dd className="truncate font-medium tabular-nums text-ink" title={v}>{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[11px] text-muted">
        Retrospective simulation of historical day-ahead decisions — not a live forecast feed. The cutoff is a configurable assumption, not a verified market deadline.
      </p>
    </section>
  );
}
