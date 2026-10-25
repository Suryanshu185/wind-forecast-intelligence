# 05 — Analytics Methodology & Algorithm Specification

Normative specification for the analytical core. Implementation must follow this document; tests encode it.
Facts about the data referenced here are established in `04-data-research-notes.md`.

The product is a **retrospective simulation of historical decision-making** for January 2026 deliveries. It is not a live feed and not a purchasing recommendation.

---

## 1. Time model

| Concept | Definition |
|---|---|
| Internal time | All instants stored/compared as timezone-aware **UTC**. Naive datetimes are rejected at the ingestion boundary. |
| Delivery date `D` | A `Europe/London` calendar date (= Elexon `settlementDate`). Allowed: 2026-01-01 … 2026-01-31 (configurable bounds). |
| Settlement period (SP) | 30-minute UTC interval `[t, t+30m)`, identified by its UTC start `t`. The unit of comparison and of "expected intervals". |
| Forecast slot | 60-minute UTC interval `[T, T+60m)` as published in WINDFOR (`startTime = T`). |
| Decision date | `D − days_before` (default `days_before = 1`), a `Europe/London` calendar date. |
| Cutoff instant `C(D)` | `localize(decision_date, cutoff_time, Europe/London)` converted to UTC via `zoneinfo`. Non-existent local times (spring-forward gap) shift forward by the gap; ambiguous local times (autumn overlap) resolve to the **first** occurrence (`fold=0`). Both are unit-tested. |
| Availability lag `L` | Minutes between `publishTime` and the moment the forecast is assumed usable. Default **0**. Effective eligibility cutoff = `C(D) − L`. |

Expected SPs for a delivery date = the 30-minute UTC instants in `[local_midnight(D), local_midnight(D+1))` → 48 normally, 46 or 50 on clock-change days. Expected total for January 2026 = **1,488**. This count comes from the calendar, **not** from the data.

## 2. Inputs & normalisation

### 2.1 Actuals (FUELHH, `fuelType == "WIND"`)
Normalised record: `(start_utc, publish_utc, mw: float | None, settlement_date, settlement_period)`.
- Parse ISO-8601 with `Z`; reject naive strings or non-UTC offsets (counted as `rejected_rows`, surfaced in data quality).
- `generation: null` → `mw = None` (missing; **never** coerced to 0). `0` is kept as a legitimate zero.
- Negative values are kept but counted (`negative_values`); none observed.
- Join key is `start_utc` **only**. `settlement_date`/`settlement_period` are kept for display and a consistency check (`settlement_date == London date of start_utc`; mismatches counted).

### 2.2 Forecasts (WINDFOR)
Normalised record: `(start_utc, publish_utc, mw: float | None)`.
- Same parsing rules. `start_utc` must have `minute == 0`; others are counted as `off_grid_rows` and excluded (none observed).

### 2.3 Duplicate and conflict handling (deterministic)
Natural keys: actuals `(start_utc)`; forecasts `(start_utc, publish_utc)`.
1. **Exact duplicates** (same key, same `mw`): collapse to one row; count `duplicate_rows_collapsed`.
2. **Conflicting duplicates** (same key, different `mw`): apply `DUPLICATE_CONFLICT_POLICY`:
   - `min` (default): keep the row with the **lowest** `mw` (conservative for procurement: lower expected wind → higher residual need). `None` loses to any number.
   - `exclude`: drop all rows for that key; the interval becomes missing.
   Count `conflicting_keys` and return up to N examples in the data-quality payload. Never silent.
3. Actuals with several rows for the same `start_utc` but different `publish_utc` (revisions): keep the **latest `publish_utc`**; ties fall to rule 2. (None observed — the API returns one row per interval.)
4. Result: at most one row per natural key, sorted by key. API response order is irrelevant (tested with shuffled input).

Observed in real January data: **0 duplicates, 0 conflicts**. The rules are exercised by synthetic fixtures (clearly named `synthetic_*`).

## 3. Forecast-vintage selection (core algorithm)

For each delivery SP `s` (UTC start) on delivery date `D = london_date(s)`:

```
slot(s)      = s floored to the hour
cutoff(D)    = C(D) − L
eligible(s)  = { f ∈ forecasts :  f.start_utc == slot(s)
                              AND f.publish_utc ≤ cutoff(D)
                              AND f.publish_utc <  slot(s)       # guard: forecast must pre-date its delivery slot
                              AND f.mw is not None }
if eligible(s) is empty:
      status = FORECAST_UNAVAILABLE ; forecast_mw = None
else:
      sel = argmax_{f ∈ eligible} f.publish_utc                  # latest eligible vintage
      status = OK ; forecast_mw = sel.mw
      forecast_published_at = sel.publish_utc
      lead_time = slot(s) − sel.publish_utc                      # > 0
```

Rules:
- **Eligibility uses `publishTime` only.** `startTime` selects the target and is never compared with the cutoff.
- A vintage published exactly at the cutoff is **eligible** (`≤`).
- Rows with `publish_utc ≥ slot(s)` (back-cast rows, observed lead time down to −25.5 h) are never eligible. This does not bind at D−1 cutoffs but protects `days_before = 0` configurations.
- After §2.3 `(start, publish)` is unique, so `argmax` is unique: no dependence on API order or wall clock.
- Selection is per forecast slot. All slots of a day normally come from one vintage because each observed vintage spans 73 consecutive hours, but nothing assumes it; the UI shows the publish time per interval.
- **Hourly → half-hourly mapping:** the selected hourly value applies to *both* SPs starting at `T` and `T+30m` (assumption A-4). The response carries `forecast_slot_start` and a resolution note so the UI states that two half-hours share one forecast. Optional later: native hourly metrics (mean of the two actual SPs).
- No eligible forecast → the SP is **unavailable** (`forecast_mw = null`), never zero.

### 3.1 Status taxonomy (per SP)
| `status` | actual present | forecast eligible | In metrics |
|---|---|---|---|
| `MATCHED` | yes | yes | **yes** |
| `FORECAST_UNAVAILABLE` | yes | no | no |
| `ACTUAL_MISSING` | no | yes | no |
| `BOTH_MISSING` | no | no | no |

Counts (all disclosed): `expected`, `actual_observed`, `forecast_available`, `matched`, `forecast_unavailable`, `actual_missing`, `both_missing`.
Tested invariant: `matched + forecast_unavailable + actual_missing + both_missing == expected`.
Rows outside the expected set are counted as `unexpected_rows` and excluded.

### 3.2 Revision exploration (`GET /intervals/{start}/revisions`)
For one SP return **all** vintages targeting its forecast slot, each with `publish_utc`, `mw`, `lead_time_h`, `eligible` (under the current cutoff), `selected`, `error_if_used = actual − mw`, and minutes before/after cutoff. Also the actual. Post-cutoff vintages are shown but marked "not available at decision time — context only".

## 4. Metrics

Over matched SPs `i = 1…n` (n = `matched`), `A_i` actual MW, `F_i` selected forecast MW:

| Metric | Formula | Unit | Notes |
|---|---|---|---|
| Signed error | `e_i = A_i − F_i` | MW | **Positive: actual exceeded forecast (under-forecast). Negative: actual below forecast (over-forecast).** Used everywhere. |
| MAE | `(1/n) Σ |e_i|` | MW | |
| RMSE | `√((1/n) Σ e_i²)` | MW | Penalises large errors; RMSE ≥ MAE. |
| Bias (mean signed error) | `(1/n) Σ e_i` | MW | Negative → forecast systematically too high. |
| P90 absolute error | 90th percentile of `|e_i|`, linear interpolation (`numpy.percentile(..., 90, method="linear")`) | MW | Definition pinned so results are reproducible. |
| Interval coverage | `matched / expected` | % | Denominator is the calendar expected count (§1). |
| nMAE (optional) | `MAE / mean(A_i)` | % | Context only; null if mean(A) = 0. |

Rules:
- Metrics use **only** `MATCHED` SPs. No imputation, zero-filling or interpolation.
- `n == 0` → all metrics `null` (never 0 or NaN in JSON); coverage still reported.
- Every metric is displayed with its `matched / expected` and coverage.
- Coverage < 95 % → "partial data" banner; < 50 % → strong warning (constants, configurable).
- float64 throughout; rounding only at presentation.
- **Daily metrics:** same definitions grouped by London delivery date; each day carries its own `expected` (46/48/50), `matched`, coverage.
- **Error distribution:** fixed-width histogram of `e_i` (default 500 MW, anchored at multiples of 500 so bins are stable across filters), quantiles (P5, P10, P25, P50, P75, P90, P95), counts of over-/under-forecast intervals.
- **Largest errors:** top *k* (default 10) matched SPs by `e_i` descending (largest under-forecasts) and ascending (largest over-forecasts); ties → earlier `start_utc`. Nice-to-have: **worst contiguous windows** — rolling mean of `e` over *w* consecutive, fully matched SPs (default 6 = 3 h), top *k* non-overlapping.
- **Elevated-error days:** daily RMSE ≥ P75 of the month's daily RMSEs (configurable), requiring ≥ 80 % daily coverage. Labelled "elevated relative to this period".

### 4.1 Worked example (golden unit test)
Matched (A, F) in MW: (100,90), (80,100), (0,10), (50,50).
`e = [10, −20, −10, 0]` → MAE = 10; RMSE = √((100+400+100+0)/4) = √150 ≈ 12.2474; Bias = −5;
P90|e|: sorted |e| = 0, 10, 10, 20 → position 0.9×3 = 2.7 → 10 + 0.7×(20−10) = **17**.
(Note the `(0,10)` row: an actual of exactly 0 MW is a valid matched value, tested separately from a `null` actual.)

## 5. Decision-intelligence analytics (illustrative)

Label everywhere: **"Analytical scenario based on historical forecast errors. Not a purchase recommendation."**
There is no demand, contract, other-generation or price data, so the app never outputs a shortfall, optimal volume, cost, saving or profit.

Define **wind under-delivery** `u_i = F_i − A_i = −e_i` (positive when wind came in below forecast — the risk direction for a buyer relying on the forecast).

1. **Empirical under-delivery buffer at confidence c** ∈ {50, 80, 90, 95 %}: `B_c = max(0, Q_c(u_i))` over matched SPs (linear-interpolated quantile). Reading: *"in c % of matched half-hours in this period, wind output was no more than B_c MW below the forecast."* Reported with n and the in-sample caveat.
2. **Error bands:** central interval `[Q_{(1−c)/2}(e), Q_{(1+c)/2}(e)]` applied to the forecast line as an optional ribbon on the Explorer chart (off by default, labelled scenario).
3. **Context breakdowns (descriptive):** error by hour of day (London), by lead-time bucket of the selected vintage, by forecast-level tercile, and elevated-error days.
4. **Rolling-origin calibration check (optional):** for each delivery day `D` with ≥ 7 prior days, compute `B_c` from delivery days **≤ D−2** (what could be known at the D−1 decision; D−1 actuals are incomplete), then report the realised share of D's matched SPs with `u_i ≤ B_c`. Show realised vs nominal c. Days with insufficient history are marked. First feature cut if time is short.
5. **Unit arithmetic only:** a buffer of B MW over one SP is `0.5 × B` MWh; the UI may show MWh-equivalents, never £.
6. **Mandatory caveats on this view:** one month (31 days; ~1,488 strongly autocorrelated half-hours, so effective independent sample ≪ 1,488); errors reflect dataset-scope differences as well as forecast skill; winter month only; hourly forecast shared across two SPs; in-sample.

## 6. Data-quality outputs
`GET /data-quality` returns: sources (dataset, endpoint, query), date range, cutoff configuration (time, tz, days_before, lag), counts (§3.1), vintage statistics (distinct vintages used; lead-time min/median/max of selected forecasts), anomalies (missing expected vintage slots, off-schedule vintages, late-published actuals), normalisation counters (§2), provenance (`data_source_mode`, `retrieved_at`, snapshot SHA-256, **`is_synthetic`**), and the static assumptions list.
Nominal-schedule checks (e.g. "8 vintages/day") are informational only, derived from observed data, and never used for selection.

## 7. Known methodological limitations (UI + README)
1. FUELHH and WINDFOR may not cover identical assets; errors partly reflect scope differences (U-1).
2. The forecast is hourly; half-hours share one value (A-4); alignment unproven (U-2).
3. `publishTime` is not proven to equal availability to a trader (A-2) → lag parameter.
4. The cutoff is a modelling choice and results are sensitive to it (MAE 1,941–2,145 MW across cutoffs in the exploratory run).
5. One winter month: no seasonal generalisation; tail statistics (P90/P95) are imprecise.
6. Actuals are as served today; later corrections are not observable (U-6).
7. In-sample buffers are descriptive, not guarantees.

## 8. Request configuration (validated; 422 on invalid)
`cutoff_time` (HH:MM), `timezone` (IANA; default Europe/London), `days_before` (0–3; default 1), `availability_lag_minutes` (0–720; default 0), `delivery_start`/`delivery_end` (within the permitted window; start ≤ end), `conflict_policy`, `confidence_levels`, `top_k`, `histogram_bin_mw`.
