import { describe, expect, it } from "vitest";
import { buildChartModel } from "@/features/explorer/chart-model";
import { fmtMw, fmtPct, NA } from "@/lib/format";
import { clampDate, DEFAULT_PARAMS, isValidDate, parseParams, toApiQuery, toSearchParams } from "@/lib/params";
import { ACTUAL_MISSING, makeIntervals, UNAVAILABLE, ZERO_ACTUAL } from "./fixtures.synthetic";

describe("date window (January 2026 only)", () => {
  it("clamps out-of-window dates and rejects invalid ones", () => {
    expect(clampDate("2025-12-31", "2026-01-01")).toBe("2026-01-01");
    expect(clampDate("2026-02-01", "2026-01-31")).toBe("2026-01-31");
    expect(clampDate("2026-01-15", "x")).toBe("2026-01-15");
    expect(clampDate("2026-02-30", "2026-01-01")).toBe("2026-01-01"); // impossible date
    expect(clampDate("garbage", "2026-01-31")).toBe("2026-01-31");
    expect(clampDate(null, "2026-01-31")).toBe("2026-01-31");
    expect(isValidDate("2026-01-31")).toBe(true);
    expect(isValidDate("2026-1-31")).toBe(false);
  });

  it("sanitises URL params: window, ordering, cutoff, ranges and enums", () => {
    const p = parseParams(new URLSearchParams("from=2027-05-05&to=2025-01-01&cutoff=99:99&daysBefore=9&lag=-5&res=weekly&align=sideways"));
    expect(p.delivery_start).toBe("2026-01-01");
    expect(p.delivery_end).toBe("2026-01-31");
    expect(p.cutoff_time).toBe("09:50");
    expect(p.days_before).toBe(1);
    expect(p.availability_lag_minutes).toBe(0);
    expect(p.resolution).toBe("half_hour");
    expect(p.hour_alignment).toBe("start");
  });

  it("swaps a reversed range instead of sending it to the API", () => {
    const p = parseParams(new URLSearchParams("from=2026-01-20&to=2026-01-10"));
    expect([p.delivery_start, p.delivery_end]).toEqual(["2026-01-10", "2026-01-20"]);
  });

  it("round-trips non-default values and keeps defaults out of the URL", () => {
    expect(toSearchParams(DEFAULT_PARAMS).toString()).toBe("");
    const custom = { ...DEFAULT_PARAMS, cutoff_time: "15:30", resolution: "hourly" as const, hour_alignment: "end" as const, availability_lag_minutes: 30 };
    expect(parseParams(toSearchParams(custom))).toEqual(custom);
  });

  it("always sends explicit analysis parameters to the API", () => {
    const q = new URLSearchParams(toApiQuery({ ...DEFAULT_PARAMS, cutoff_time: "09:20" }));
    expect(q.get("cutoff_time")).toBe("09:20");
    expect(q.get("delivery_start")).toBe("2026-01-01");
    expect(q.get("hour_alignment")).toBe("start");
    expect(q.get("days_before")).toBe("1");
  });
});

describe("chart model: missing is a gap, zero is a value", () => {
  const data = makeIntervals(8, { 2: UNAVAILABLE, 3: UNAVAILABLE, 5: ACTUAL_MISSING, 6: ZERO_ACTUAL });
  const model = buildChartModel(data.intervals);

  it("keeps null for missing values and 0 for real zeros", () => {
    expect(model.points[2]!.forecast).toBeNull();
    expect(model.points[5]!.actual).toBeNull();
    expect(model.points[6]!.actual).toBe(0);
    expect(model.points[6]!.actual).not.toBeNull();
  });

  it("merges consecutive unavailable intervals into one shaded range", () => {
    expect(model.forecastGaps).toHaveLength(1);
    const g = model.forecastGaps[0]!;
    expect(g.to - g.from).toBe(2 * 30 * 60_000);
    expect(model.actualGaps).toHaveLength(1);
  });

  it("has no gaps when everything is present", () => {
    const m = buildChartModel(makeIntervals(4).intervals);
    expect(m.forecastGaps).toEqual([]);
    expect(m.actualGaps).toEqual([]);
  });
});

describe("formatting never turns missing into zero", () => {
  it("renders null/undefined as an em dash", () => {
    expect(fmtMw(null)).toBe(NA);
    expect(fmtMw(undefined)).toBe(NA);
    expect(fmtPct(null)).toBe(NA);
    expect(fmtMw(0)).toBe("0 MW");
  });
  it("uses an explicit sign when asked", () => {
    expect(fmtMw(-1840.4, { signed: true })).toBe("−1,840 MW");
    expect(fmtMw(25.2, { signed: true })).toBe("+25 MW");
    expect(fmtMw(1234.5, { unit: false })).toBe("1,235");
  });
});
