import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Interval, Resolution } from "@/api/types";
import { fmtLocal, fmtMw, fmtUtc } from "@/lib/format";
import { buildChartModel } from "./chart-model";

export const COLOURS = { actual: "#3dd6c6", forecast: "#f5b84a", grid: "#263553", axis: "#9aa8c2" };

const hhmm = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hour12: false });
const dd = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "2-digit", month: "short" });

function ChartTooltip({ active, payload, intervals }: { active?: boolean; payload?: Array<{ payload: { index: number } }>; intervals: Interval[] }) {
  if (!active || !payload?.length) return null;
  const i = intervals[payload[0]!.payload.index];
  if (!i) return null;
  return (
    <div className="max-w-[18rem] rounded-md border border-border bg-raised px-3 py-2 text-xs shadow-lg" data-testid="chart-tooltip">
      <p className="font-medium text-ink">{fmtLocal(i.start_utc)} <span className="text-muted">(London)</span></p>
      <p className="text-muted">{fmtUtc(i.start_utc)}</p>
      <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        <dt style={{ color: COLOURS.actual }}>Actual</dt>
        <dd className="text-right tabular-nums">{i.actual_mw === null ? "missing" : fmtMw(i.actual_mw)}</dd>
        <dt style={{ color: COLOURS.forecast }}>Forecast</dt>
        <dd className="text-right tabular-nums">{i.forecast_mw === null ? "unavailable" : fmtMw(i.forecast_mw)}</dd>
        <dt className="text-muted">Error</dt>
        <dd className="text-right tabular-nums">{i.error_mw === null ? "—" : fmtMw(i.error_mw, { signed: true })}</dd>
        {i.forecast_published_at ? (
          <>
            <dt className="text-muted">Published</dt>
            <dd className="text-right tabular-nums">{fmtLocal(i.forecast_published_at)}</dd>
          </>
        ) : null}
      </dl>
      <p className="mt-1 text-[11px] text-muted">Click to inspect · error = actual − forecast</p>
    </div>
  );
}

export function ForecastChart({
  intervals,
  selectedStart,
  onSelect,
  resolution,
  height = 360,
}: {
  intervals: Interval[];
  selectedStart: string | null;
  onSelect: (startUtc: string) => void;
  resolution: Resolution;
  height?: number;
}) {
  const model = useMemo(() => buildChartModel(intervals), [intervals]);
  const selectedT = selectedStart ? Date.parse(selectedStart) : null;
  const spanDays = intervals.length ? (Date.parse(intervals.at(-1)!.end_utc) - Date.parse(intervals[0]!.start_utc)) / 86_400_000 : 0;

  const formatTick = (t: number) => (spanDays > 2 ? dd.format(new Date(t)) : hhmm.format(new Date(t)));

  return (
    <div data-testid="forecast-chart" data-points={model.points.length} data-forecast-gaps={model.forecastGaps.length} data-actual-gaps={model.actualGaps.length}>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          data={model.points}
          margin={{ top: 8, right: 12, bottom: 4, left: 4 }}
          onClick={(state) => {
            const label = (state as { activeLabel?: number | string } | undefined)?.activeLabel;
            if (label === undefined) return;
            const t = Number(label);
            let best = model.points[0];
            for (const p of model.points) if (best && Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
            const hit = best ? intervals[best.index] : undefined;
            if (hit) onSelect(hit.start_utc);
          }}
        >
          <defs>
            <pattern id="hatch-forecast-gap" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="8" height="8" fill="#f5b84a" fillOpacity="0.06" />
              <line x1="0" y1="0" x2="0" y2="8" stroke="#f5b84a" strokeOpacity="0.5" strokeWidth="2" />
            </pattern>
            <pattern id="hatch-actual-gap" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
              <rect width="8" height="8" fill="#7cc4ff" fillOpacity="0.06" />
              <line x1="0" y1="0" x2="0" y2="8" stroke="#7cc4ff" strokeOpacity="0.5" strokeWidth="2" />
            </pattern>
          </defs>
          <CartesianGrid stroke={COLOURS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={formatTick}
            stroke={COLOURS.axis}
            tick={{ fontSize: 11 }}
            minTickGap={36}
            label={{ value: spanDays > 2 ? "Delivery date (Europe/London)" : "Delivery time (Europe/London)", position: "insideBottom", offset: -2, fill: COLOURS.axis, fontSize: 11 }}
            height={40}
          />
          <YAxis
            stroke={COLOURS.axis}
            tick={{ fontSize: 11 }}
            domain={[0, "auto"]}
            tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
            width={44}
            label={{ value: "MW", angle: -90, position: "insideLeft", fill: COLOURS.axis, fontSize: 11 }}
          />
          <Tooltip content={<ChartTooltip intervals={intervals} />} isAnimationActive={false} />
          {model.forecastGaps.map((g) => (
            <ReferenceArea key={`f${g.from}`} x1={g.from} x2={g.to} fill="url(#hatch-forecast-gap)" strokeOpacity={0} ifOverflow="hidden" />
          ))}
          {model.actualGaps.map((g) => (
            <ReferenceArea key={`a${g.from}`} x1={g.from} x2={g.to} fill="url(#hatch-actual-gap)" strokeOpacity={0} ifOverflow="hidden" />
          ))}
          {selectedT !== null ? <ReferenceLine x={selectedT} stroke="#e6ecf7" strokeDasharray="4 3" /> : null}
          <Line
            name="Forecast (WINDFOR, selected vintage)"
            dataKey="forecast"
            stroke={COLOURS.forecast}
            strokeWidth={2}
            strokeDasharray={resolution === "half_hour" ? "6 3" : undefined}
            type="stepAfter"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          <Line
            name="Actual (FUELHH)"
            dataKey="actual"
            stroke={COLOURS.actual}
            strokeWidth={2}
            type="stepAfter"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ChartLegend({ hasForecastGap, hasActualGap, resolution }: { hasForecastGap: boolean; hasActualGap: boolean; resolution: Resolution }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted" aria-label="Chart legend">
      <li className="flex items-center gap-2">
        <span aria-hidden className="h-0.5 w-6" style={{ background: COLOURS.actual }} /> Actual (FUELHH)
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden className="w-6 border-t-2 border-dashed" style={{ borderColor: COLOURS.forecast }} />
        Forecast (WINDFOR, vintage known at cutoff){resolution === "half_hour" ? " — one hourly value per two half-hours" : ""}
      </li>
      {hasForecastGap ? (
        <li className="flex items-center gap-2">
          <span aria-hidden className="size-3 rounded-sm border border-forecast/60 bg-forecast/20" /> Forecast unavailable (not zero)
        </li>
      ) : null}
      {hasActualGap ? (
        <li className="flex items-center gap-2">
          <span aria-hidden className="size-3 rounded-sm border border-under/60 bg-under/20" /> Actual missing (not zero)
        </li>
      ) : null}
    </ul>
  );
}
