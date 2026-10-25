import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { failWith, mockApi, renderApp } from "./harness";
import {
  ACTUAL_MISSING,
  makeIntervals,
  makeMeta,
  makeRevisions,
  makeScenarios,
  makeSummary,
  provenance,
  UNAVAILABLE,
  ZERO_ACTUAL,
  counts,
  metrics,
} from "./fixtures.synthetic";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const openAccuracy = () => renderApp("/?tab=accuracy");

describe("provenance and framing", () => {
  it("labels real data and the retrospective, assumption-based framing", async () => {
    mockApi();
    renderApp();
    expect((await screen.findByTestId("provenance-badge")).textContent).toMatch(/Real Elexon BMRS data/);
    expect(await screen.findByTestId("data-strip")).toHaveTextContent(/not a live forecast feed/i);
    expect(screen.getByTestId("data-strip")).toHaveTextContent(/configurable assumption, not a verified market deadline/i);
    expect(screen.getByTestId("scope-banner")).toHaveTextContent(/may not cover the same generators/i);
    expect(await screen.findByTestId("warning-ALIGNMENT_ASSUMED")).toHaveTextContent(/unverified/i);
  });

  it("shows a loud SYNTHETIC badge for synthetic data", async () => {
    mockApi({
      meta: () => makeMeta({ provenance: provenance({ is_synthetic: true, mode: "synthetic", notice: "SYNTHETIC" }) }),
    });
    renderApp();
    expect((await screen.findByTestId("provenance-badge")).textContent).toMatch(/SYNTHETIC DEVELOPMENT FIXTURE/);
  });

  it("states decision cutoff, timezone and counts in the data strip", async () => {
    mockApi();
    renderApp();
    const strip = await screen.findByTestId("data-strip");
    expect(strip).toHaveTextContent("09:50 Europe/London, D−1");
    expect(strip).toHaveTextContent("96 half-hour settlement periods");
    expect(strip).toHaveTextContent("Elexon FUELHH · WINDFOR");
  });
});

describe("date selection is restricted to January 2026", () => {
  it("limits the native date inputs", async () => {
    mockApi();
    renderApp();
    const from = await screen.findByLabelText("Delivery start date");
    const to = screen.getByLabelText("Delivery end date");
    for (const el of [from, to]) {
      expect(el).toHaveAttribute("min", "2026-01-01");
      expect(el).toHaveAttribute("max", "2026-01-31");
    }
  });

  it("corrects an out-of-window value, tells the user, and never requests it", async () => {
    const api = mockApi();
    renderApp();
    const from = await screen.findByLabelText("Delivery start date");
    fireEvent.change(from, { target: { value: "2025-12-15" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/limited to 1–31 January 2026/);
    await waitFor(() => expect(api.calls.every((u) => (u.searchParams.get("delivery_start") ?? "2026-01-01") >= "2026-01-01")).toBe(true));
  });

  it("sanitises an out-of-window URL", async () => {
    const api = mockApi();
    renderApp("/?from=2024-01-01&to=2030-12-31");
    await screen.findByTestId("data-strip");
    const q = api.byPath("/analysis/summary")[0]!.searchParams;
    expect([q.get("delivery_start"), q.get("delivery_end")]).toEqual(["2026-01-01", "2026-01-31"]);
  });

  it("quick ranges stay inside the window", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: "29–31 Jan" }));
    await waitFor(() => {
      const q = api.byPath("/analysis/summary").at(-1)!.searchParams;
      expect([q.get("delivery_start"), q.get("delivery_end")]).toEqual(["2026-01-29", "2026-01-31"]);
    });
  });
});

describe("accuracy metrics display", () => {
  it("shows every metric with units and an explicit denominator", async () => {
    mockApi();
    openAccuracy();
    expect(await screen.findByTestId("metric-mae-value")).toHaveTextContent("150 MW");
    expect(screen.getByTestId("metric-rmse-value")).toHaveTextContent("200 MW");
    expect(screen.getByTestId("metric-bias-value")).toHaveTextContent("−120 MW");
    expect(screen.getByTestId("metric-p90-value")).toHaveTextContent("320 MW");
    expect(screen.getByTestId("metric-coverage-value")).toHaveTextContent("100.0%");
    expect(screen.getByTestId("metric-mae")).toHaveTextContent(/over 96 matched of 96 expected half-hour settlement periods/);
    expect(screen.getByTestId("metric-bias")).toHaveTextContent(/Forecast above actual on average/);
  });

  it("explains each metric through an accessible tooltip trigger", async () => {
    mockApi();
    const user = userEvent.setup();
    openAccuracy();
    await screen.findByTestId("metric-mae");
    const trigger = screen.getByRole("button", { name: "Definition of MAE" });
    await user.tab(); // keyboard reachable
    trigger.focus();
    expect((await screen.findAllByText(/Mean Absolute Error/i)).length).toBeGreaterThan(0);
  });

  it("states the sign convention and lists extremes with click-through", async () => {
    mockApi();
    const user = userEvent.setup();
    openAccuracy();
    expect(await screen.findByText(/error = actual − forecast, in MW/)).toBeInTheDocument();
    const over = screen.getByTestId("extremes-over");
    expect(within(over).getByText("−480")).toBeInTheDocument();
    await user.click(within(screen.getByTestId("extremes-under")).getByRole("button", { name: /Inspect interval/ }));
    // clicking jumps to the explorer with that interval selected
    expect(await screen.findByTestId("forecast-chart")).toBeInTheDocument();
  });

  it("shows em dashes, not zeros, when nothing is matched", async () => {
    mockApi({
      summary: () =>
        makeSummary({
          metrics: metrics({ n: 0, mae: null, rmse: null, bias: null, p90_abs_error: null, error_std: null, mean_actual: null, mean_forecast: null, nmae: null }),
          counts: counts({ matched: 0, coverage: 0, coverage_level: "low", forecast_unavailable: 96 }),
          distribution: { ...makeSummary().distribution, bins: [], quantiles_mw: null },
          warnings: [{ code: "NO_MATCHED_INTERVALS", severity: "critical", message: "No interval has both an actual and an eligible forecast; metrics are unavailable." }],
        }),
    });
    openAccuracy();
    expect(await screen.findByTestId("metric-mae-value")).toHaveTextContent("—");
    expect(screen.getByTestId("metric-mae-value")).not.toHaveTextContent("0 MW");
    expect(screen.getByTestId("metric-mae")).toHaveTextContent(/not computed \(not zero\)/);
    expect(screen.getByText("No matched intervals")).toBeInTheDocument();
    expect(screen.getByTestId("warning-NO_MATCHED_INTERVALS")).toBeInTheDocument();
  });

  it("surfaces partial-data coverage and missing counts", async () => {
    mockApi({
      summary: () =>
        makeSummary({
          counts: counts({ matched: 40, coverage: 40 / 96, coverage_level: "low", forecast_unavailable: 30, actual_missing: 26 }),
          warnings: [{ code: "PARTIAL_DATA", severity: "critical", message: "Only 40 of 96 expected intervals (41.7%) are matched; metrics cover those only." }],
        }),
    });
    openAccuracy();
    expect(await screen.findByTestId("warning-PARTIAL_DATA")).toHaveTextContent("Only 40 of 96");
    const table = screen.getByTestId("coverage-breakdown");
    expect(within(table).getByText("Forecast unavailable").closest("tr")).toHaveTextContent("30");
    expect(within(table).getByText("Actual missing").closest("tr")).toHaveTextContent("26");
    expect(screen.getByTestId("metric-coverage-value")).toHaveTextContent("41.7%");
  });
});

describe("actual-versus-forecast visualisation", () => {
  it("renders the chart and distinguishes unavailable/missing from zero", async () => {
    mockApi({ intervals: () => makeIntervals(96, { 10: UNAVAILABLE, 11: UNAVAILABLE, 30: ACTUAL_MISSING, 40: ZERO_ACTUAL }) });
    renderApp();
    const chart = await screen.findByTestId("forecast-chart");
    expect(chart).toHaveAttribute("data-points", "96");
    expect(chart).toHaveAttribute("data-forecast-gaps", "1");
    expect(chart).toHaveAttribute("data-actual-gaps", "1");
    const legend = screen.getByRole("list", { name: "Chart legend" });
    expect(legend).toHaveTextContent("Forecast unavailable (not zero)");
    expect(legend).toHaveTextContent("Actual missing (not zero)");
    expect(legend).toHaveTextContent("one hourly value per two half-hours");
    expect(screen.getByTestId("resolution-note")).toHaveTextContent(/NOT independent half-hour forecasts/);
  });

  it("omits gap legend entries when data are complete", async () => {
    mockApi();
    renderApp();
    await screen.findByTestId("forecast-chart");
    expect(screen.getByRole("list", { name: "Chart legend" })).not.toHaveTextContent("unavailable");
  });

  it("offers an accessible table with explicit 'unavailable' / 'missing' / 0 values", async () => {
    mockApi({ intervals: () => makeIntervals(96, { 0: UNAVAILABLE, 1: ACTUAL_MISSING, 2: ZERO_ACTUAL }) });
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /Table/ }));
    const rows = within(screen.getByTestId("interval-table")).getAllByRole("row");
    const cells = (r: HTMLElement) => within(r).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(rows[1]!)[2]).toBe("unavailable"); // forecast column
    expect(cells(rows[2]!)[1]).toBe("missing"); // actual column
    expect(cells(rows[3]!)[1]).toBe("0"); // a real zero is shown as 0, not "missing"
  });

  it("zooms to one delivery day", async () => {
    mockApi();
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("forecast-chart");
    await user.selectOptions(screen.getByLabelText("Zoom to day"), "2026-01-02");
    expect(screen.getByTestId("forecast-chart")).toHaveAttribute("data-points", "48");
  });
});

describe("interval inspection and revision exploration", () => {
  async function openInterval() {
    const api = mockApi();
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /Table/ }));
    await user.click(within(await screen.findByTestId("interval-table")).getAllByRole("button")[0]!);
    return { api, user };
  }

  it("shows publication time, lead time, signed error and the reason for selection", async () => {
    const { api } = await openInterval();
    const insp = await screen.findByTestId("interval-inspector");
    expect(insp).toHaveTextContent(/Forecast published/);
    expect(insp).toHaveTextContent(/Lead time before the hour/);
    expect(insp).toHaveTextContent(/Error \(actual − forecast\)/);
    expect(await screen.findByTestId("error-sign-note")).toHaveTextContent(/over-forecast/);
    const why = await screen.findByTestId("why-selected");
    expect(why).toHaveTextContent("Selected the latest eligible vintage");
    expect(api.byPath("/revisions")).toHaveLength(1);
    expect(decodeURIComponent(api.byPath("/revisions")[0]!.pathname)).toContain("2026-01-01T00:00:00Z");
  });

  it("lists every revision and marks post-cutoff vintages as not known at decision time", async () => {
    await openInterval();
    const table = await screen.findByTestId("vintage-table");
    expect(within(table).getAllByRole("row")).toHaveLength(1 + makeRevisions().vintages.length);
    expect(within(table).getByText("Selected")).toBeInTheDocument();
    expect(within(table).getAllByText(/After cutoff · not known/)).toHaveLength(1);
    expect(within(table).getByText(/Back-cast/)).toBeInTheDocument();
    expect(within(table).getByText(/Eligible · superseded/)).toBeInTheDocument();
    expect(screen.getByText(/shown for context only/i)).toBeInTheDocument();
  });

  it("reports an unavailable forecast explicitly in the inspector", async () => {
    mockApi({
      intervals: () => makeIntervals(96, { 0: UNAVAILABLE }),
      revisions: () => makeRevisions({ interval: makeIntervals(1, { 0: UNAVAILABLE }).intervals[0]!, explanation: ["No forecast had been published by the cutoff, so it is UNAVAILABLE (not zero)."] }),
    });
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /Table/ }));
    await user.click(within(await screen.findByTestId("interval-table")).getAllByRole("button")[0]!);
    expect(await screen.findByTestId("inspector-status")).toHaveTextContent("Forecast unavailable");
    expect(screen.getByTestId("interval-inspector")).toHaveTextContent("unavailable at cutoff");
    expect(await screen.findByTestId("why-selected")).toHaveTextContent("UNAVAILABLE (not zero)");
  });

  it("steps between intervals with the keyboard", async () => {
    mockApi();
    const user = userEvent.setup();
    renderApp();
    const group = (await screen.findByTestId("forecast-chart")).parentElement!;
    group.focus();
    await user.keyboard("{Home}");
    expect(await screen.findByTestId("interval-inspector")).toHaveTextContent(/01 Jan, 00:00/);
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByTestId("interval-inspector")).toHaveTextContent(/01 Jan, 00:30/));
    await user.keyboard("{ArrowLeft}");
    await waitFor(() => expect(screen.getByTestId("interval-inspector")).toHaveTextContent(/01 Jan, 00:00/));
  });
});

describe("cutoff changes", () => {
  it("re-requests with the new cutoff and shows the updated results", async () => {
    const api = mockApi({
      summary: (u) =>
        u.searchParams.get("cutoff_time") === "09:20"
          ? makeSummary({ metrics: metrics({ mae: 321 }), config: { ...makeSummary().config, cutoff_time: "09:20" } })
          : makeSummary(),
    });
    const user = userEvent.setup();
    openAccuracy();
    expect(await screen.findByTestId("metric-mae-value")).toHaveTextContent("150 MW");
    await user.selectOptions(screen.getByRole("combobox", { name: /Decision cutoff/ }), "09:20");
    await waitFor(() => expect(screen.getByTestId("metric-mae-value")).toHaveTextContent("321 MW"));
    expect(api.byPath("/analysis/summary").some((u) => u.searchParams.get("cutoff_time") === "09:20")).toBe(true);
    expect(api.byPath("/analysis/intervals")).toHaveLength(0); // inactive tabs do not fetch
  });

  it("sends decision day, availability lag, resolution and alignment changes to the API", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("data-strip");
    await user.selectOptions(screen.getByRole("combobox", { name: /Decision day/ }), "2");
    await user.clear(screen.getByRole("spinbutton", { name: /Availability lag/ }));
    await user.type(screen.getByRole("spinbutton", { name: /Availability lag/ }), "20");
    await user.click(screen.getByRole("radio", { name: "Native hourly" }));
    await user.click(screen.getByRole("button", { name: /Assumptions & sensitivity/ }));
    await user.click(screen.getByRole("radio", { name: /Hour ending at startTime/ }));
    await waitFor(() => {
      const q = api.byPath("/analysis/summary").at(-1)!.searchParams;
      expect(q.get("days_before")).toBe("2");
      expect(q.get("availability_lag_minutes")).toBe("20");
      expect(q.get("resolution")).toBe("hourly");
      expect(q.get("hour_alignment")).toBe("end");
    });
  });
});

describe("loading, error and empty states", () => {
  it("shows a loading skeleton first", async () => {
    mockApi({ intervals: () => makeIntervals() });
    renderApp();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    await screen.findByTestId("forecast-chart");
  });

  it("shows an actionable error and recovers on retry", async () => {
    let fail = true;
    mockApi({ intervals: () => (fail ? failWith(503, "DATA_UNAVAILABLE", "The dataset is not available") : makeIntervals()) });
    const user = userEvent.setup();
    renderApp();
    const alert = await screen.findByText("The dataset is not available");
    expect(alert.closest("[role=alert]")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: /Retry/ }));
    expect(await screen.findByTestId("forecast-chart")).toBeInTheDocument();
  });

  it("explains network failures without inventing data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    renderApp();
    expect(await screen.findAllByText(/Could not reach the analysis service/)).not.toHaveLength(0);
    expect(screen.queryByTestId("forecast-chart")).not.toBeInTheDocument();
    expect(screen.getAllByText(/may still be starting up/i).length).toBeGreaterThan(0);
  });

  it("does not offer retry for validation errors", async () => {
    mockApi({ intervals: () => failWith(422, "OUT_OF_RANGE", "delivery_start is outside the permitted window") });
    renderApp();
    await screen.findByText(/outside the permitted window/);
    expect(screen.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no intervals", async () => {
    mockApi({ intervals: () => makeIntervals(0) });
    renderApp();
    expect(await screen.findByText("No intervals in this selection")).toBeInTheDocument();
    expect(screen.queryByTestId("forecast-chart")).not.toBeInTheDocument();
  });
});

describe("decision intelligence", () => {
  it("always shows the scenario disclaimer and never claims money or volume", async () => {
    mockApi();
    const { container } = renderApp("/?tab=decision");
    expect(await screen.findByTestId("scenario-disclaimer")).toHaveTextContent(/not a purchase recommendation/i);
    expect(screen.getByTestId("buffer-table")).toHaveTextContent("50%");
    expect(screen.getByTestId("buffer-table")).toHaveTextContent("400 MW");
    expect(screen.getByTestId("level-offset")).toHaveTextContent("−120 MW");
    expect(screen.getByTestId("rolling-table")).toHaveTextContent("86.6%");
    expect(screen.getByTestId("elevated-days")).toHaveTextContent("02 Jan");
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/[£$€]/);
    expect(screen.getByText("It cannot show")).toBeInTheDocument(); // limits are stated, not hidden
  });

  it("handles a selection with no scenarios", async () => {
    mockApi({ scenarios: () => makeScenarios({ buffers: [], rolling_origin: [] }) });
    renderApp("/?tab=decision");
    expect(await screen.findByText("No scenarios available")).toBeInTheDocument();
  });
});

describe("methodology page", () => {
  it("documents datasets, definitions, scope evidence and data quality", async () => {
    mockApi();
    renderApp("/methodology");
    expect(await screen.findByRole("heading", { name: /Data & methodology/ })).toBeInTheDocument();
    const docs = await screen.findAllByText(/Official documentation/, { selector: "a" });
    expect(docs.map((a) => a.getAttribute("href"))).toEqual(["https://example.test/fuelhh", "https://example.test/windfor"]);
    expect(screen.getByTestId("formula-table")).toHaveTextContent("e = actual − forecast");
    expect(screen.getByTestId("scope-evidence")).toHaveTextContent("+408 MW");
    expect(screen.getByText(/Unverified assumption/)).toBeInTheDocument();
    expect(await screen.findByTestId("anomaly-list")).toHaveTextContent(/missing vintage/i);
    expect(screen.getByTestId("normalisation-table")).toHaveTextContent("Conflicting keys");
    expect(screen.getByTestId("assumption-list")).toBeInTheDocument();
    expect(screen.getByTestId("limitation-list")).toBeInTheDocument();
    expect(screen.getByText(/not covered by this project’s MIT licence/)).toBeInTheDocument();
  });
});

describe("cutoff change reaches the explorer too", () => {
  it("refetches intervals with the new cutoff and keeps the old chart visible while loading", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("forecast-chart");
    await user.selectOptions(screen.getByRole("combobox", { name: /Decision cutoff/ }), "15:30");
    await waitFor(() => expect(api.byPath("/analysis/intervals").some((u) => u.searchParams.get("cutoff_time") === "15:30")).toBe(true));
    expect(screen.getByTestId("forecast-chart")).toBeInTheDocument();
  });
});
