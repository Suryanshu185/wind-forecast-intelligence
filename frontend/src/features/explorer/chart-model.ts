import type { Interval } from "@/api/types";

export interface ChartPoint {
  t: number; // epoch ms of interval start
  actual: number | null;
  forecast: number | null;
  index: number;
}

export interface GapRange {
  from: number;
  to: number;
}

export interface ChartModel {
  points: ChartPoint[];
  /** Ranges where no forecast could be selected (shaded; never drawn as zero). */
  forecastGaps: GapRange[];
  /** Ranges where the actual is missing. */
  actualGaps: GapRange[];
}

function ranges(intervals: Interval[], isGap: (i: Interval) => boolean): GapRange[] {
  const out: GapRange[] = [];
  let open: GapRange | null = null;
  for (const i of intervals) {
    const start = Date.parse(i.start_utc);
    const end = Date.parse(i.end_utc);
    if (isGap(i)) {
      if (open && open.to === start) open.to = end;
      else {
        open = { from: start, to: end };
        out.push(open);
      }
    } else {
      open = null;
    }
  }
  return out;
}

/**
 * Pure transformation from API intervals to chart data.
 * Missing values stay `null` (a break in the line); zero stays 0 (a real value).
 */
export function buildChartModel(intervals: Interval[]): ChartModel {
  return {
    points: intervals.map((i, index) => ({
      t: Date.parse(i.start_utc),
      actual: i.actual_mw,
      forecast: i.forecast_mw,
      index,
    })),
    forecastGaps: ranges(intervals, (i) => i.forecast_mw === null),
    actualGaps: ranges(intervals, (i) => i.actual_mw === null),
  };
}
