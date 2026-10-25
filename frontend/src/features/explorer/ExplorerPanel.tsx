import { CalendarDays, ChevronLeft, ChevronRight, LineChart as LineChartIcon, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useIntervals } from "@/api/hooks";
import type { Interval } from "@/api/types";
import { AsyncPanel, EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { fmtDate, fmtLocal, fmtMw, NA } from "@/lib/format";
import type { AnalysisParams } from "@/lib/params";
import { useSelectedInterval } from "@/lib/use-params";
import { buildChartModel } from "./chart-model";
import { ChartLegend, ForecastChart } from "./ForecastChart";
import { IntervalInspector } from "./IntervalInspector";

const PAGE = 48;

function IntervalTable({ rows, selected, onSelect }: { rows: Interval[]; selected: string | null; onSelect: (s: string) => void }) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const safe = Math.min(page, pages - 1);
  const slice = rows.slice(safe * PAGE, safe * PAGE + PAGE);
  return (
    <div data-testid="interval-table-wrap">
      <div className="max-h-[22rem] overflow-auto" tabIndex={0} role="region" aria-label="Interval data table">
        <table className="w-full min-w-[36rem] text-left text-xs" data-testid="interval-table">
          <caption className="sr-only">Actual versus forecast for each interval (MW). error = actual − forecast.</caption>
          <thead className="sticky top-0 bg-surface text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Start (London)</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Actual</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Forecast</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Error</th>
              <th scope="col" className="py-1.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr key={r.start_utc} aria-selected={selected === r.start_utc} className={selected === r.start_utc ? "bg-actual/10" : "hover:bg-raised/50"}>
                <td className="py-1 pr-3">
                  <button type="button" className="underline-offset-2 hover:underline" onClick={() => onSelect(r.start_utc)}>{fmtLocal(r.start_utc)}</button>
                </td>
                <td className="py-1 pr-3 text-right tabular-nums">{r.actual_mw === null ? "missing" : fmtMw(r.actual_mw, { unit: false })}</td>
                <td className="py-1 pr-3 text-right tabular-nums">{r.forecast_mw === null ? "unavailable" : fmtMw(r.forecast_mw, { unit: false })}</td>
                <td className="py-1 pr-3 text-right tabular-nums">{r.error_mw === null ? NA : fmtMw(r.error_mw, { signed: true, unit: false })}</td>
                <td className="py-1 text-muted">{r.status.replace("_", " ").toLowerCase()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-muted">
        <span>Rows {safe * PAGE + 1}–{Math.min(rows.length, (safe + 1) * PAGE)} of {rows.length} · MW</span>
        <span className="flex gap-1">
          <Button variant="ghost" disabled={safe === 0} onClick={() => setPage(safe - 1)}>Previous page</Button>
          <Button variant="ghost" disabled={safe >= pages - 1} onClick={() => setPage(safe + 1)}>Next page</Button>
        </span>
      </div>
    </div>
  );
}

export function ExplorerPanel({ params }: { params: AnalysisParams }) {
  const q = useIntervals(params);
  const [selectedStart, setSelected] = useSelectedInterval();
  const [zoomDate, setZoomDate] = useState<string | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");

  const all = q.data?.intervals;
  const dates = useMemo(() => [...new Set((all ?? []).map((i) => i.delivery_date))], [all]);
  // leave a zoom that is no longer inside the selected range
  useEffect(() => {
    if (zoomDate && !dates.includes(zoomDate)) setZoomDate(null);
  }, [dates, zoomDate]);

  const visible = useMemo(() => (zoomDate ? (all ?? []).filter((i) => i.delivery_date === zoomDate) : (all ?? [])), [all, zoomDate]);
  const idx = selectedStart ? visible.findIndex((i) => i.start_utc === selectedStart) : -1;
  const selected = idx >= 0 ? visible[idx]! : null;
  const gaps = useMemo(() => buildChartModel(visible), [visible]);

  const step = (d: -1 | 1) => {
    const next = visible[(idx < 0 ? (d === 1 ? -1 : visible.length) : idx) + d];
    if (next) setSelected(next.start_utc);
  };
  const zi = zoomDate ? dates.indexOf(zoomDate) : -1;

  return (
    <Card aria-labelledby="explorer-title">
      <CardHeader
        id="explorer-title"
        title="Forecast Explorer"
        subtitle="Actual wind generation versus the forecast that was available at the decision cutoff."
        actions={
          <div className="flex items-center gap-1" role="group" aria-label="View mode">
            <Button variant={view === "chart" ? "primary" : "outline"} aria-pressed={view === "chart"} onClick={() => setView("chart")}>
              <LineChartIcon className="size-4" aria-hidden /> Chart
            </Button>
            <Button variant={view === "table" ? "primary" : "outline"} aria-pressed={view === "table"} onClick={() => setView("table")}>
              <Table2 className="size-4" aria-hidden /> Table
            </Button>
          </div>
        }
      />
      <CardBody>
        <AsyncPanel
          query={q}
          label="Loading intervals"
          skeletonClassName="h-[28rem]"
          isEmpty={(d) => d.intervals.length === 0}
          empty={<EmptyState title="No intervals in this selection">Choose a delivery range inside January 2026.</EmptyState>}
        >
          {(data) => (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Zoom to a delivery day">
                  <CalendarDays className="size-4 text-muted" aria-hidden />
                  <Button variant={zoomDate ? "outline" : "primary"} aria-pressed={!zoomDate} onClick={() => setZoomDate(null)}>Full range</Button>
                  <Button variant="ghost" aria-label="Previous day" disabled={dates.length < 2 || zi === 0} onClick={() => setZoomDate(dates[zi < 0 ? 0 : zi - 1]!)}><ChevronLeft className="size-4" aria-hidden /></Button>
                  <select
                    aria-label="Zoom to day"
                    className="h-9 rounded-md border border-border bg-bg px-2 text-sm"
                    value={zoomDate ?? ""}
                    onChange={(e) => setZoomDate(e.target.value || null)}
                  >
                    <option value="">All {dates.length} day(s)</option>
                    {dates.map((d) => <option key={d} value={d}>{fmtDate(d)}</option>)}
                  </select>
                  <Button variant="ghost" aria-label="Next day" disabled={dates.length < 2 || zi === dates.length - 1} onClick={() => setZoomDate(dates[zi < 0 ? 0 : zi + 1]!)}><ChevronRight className="size-4" aria-hidden /></Button>
                  <Badge className="ml-auto">{data.counts.matched.toLocaleString("en-GB")} of {data.counts.expected.toLocaleString("en-GB")} {data.counts.unit} matched</Badge>
                </div>

                {view === "chart" ? (
                  <div
                    tabIndex={0}
                    role="group"
                    aria-label="Actual versus forecast chart. Use the left and right arrow keys to move between intervals, Home and End to jump."
                    onKeyDown={(e) => {
                      if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
                      else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
                      else if (e.key === "Home" && visible[0]) { e.preventDefault(); setSelected(visible[0].start_utc); }
                      else if (e.key === "End" && visible.length) { e.preventDefault(); setSelected(visible[visible.length - 1]!.start_utc); }
                    }}
                    className="rounded-lg focus-visible:outline-2"
                  >
                    <ForecastChart intervals={visible} selectedStart={selectedStart} onSelect={setSelected} resolution={params.resolution} />
                  </div>
                ) : (
                  <IntervalTable rows={visible} selected={selectedStart} onSelect={setSelected} />
                )}
                <ChartLegend hasForecastGap={gaps.forecastGaps.length > 0} hasActualGap={gaps.actualGaps.length > 0} resolution={params.resolution} />
                <p className="text-xs text-muted" data-testid="resolution-note">{data.resolution_note}</p>
              </div>
              <aside aria-label="Interval inspector" className="min-w-0 rounded-lg border border-border/70 bg-bg/40 p-4">
                <IntervalInspector interval={selected} params={params} onStep={step} canPrev={idx > 0} canNext={idx >= 0 && idx < visible.length - 1} />
              </aside>
            </div>
          )}
        </AsyncPanel>
      </CardBody>
    </Card>
  );
}
