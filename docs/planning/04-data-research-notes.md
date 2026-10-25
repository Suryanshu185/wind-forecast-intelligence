# 04 — Data Source Research & Validation Notes

Status: **planning phase**. Investigated 2026-10-25 (system date) against the live Elexon Insights API.
Reproduce with `python3 docs/planning/research/probe_elexon.py` (stdlib only; output of the run used here is in
`research/probe_output.txt`). Every number below labelled **[V]** was observed in a real API response.
Items labelled **[A]** are assumptions and **[?]** are unresolved questions. Nothing here is synthetic.

Legend: **[V]** verified from live API response or official page · **[D]** stated in official documentation/OpenAPI spec ·
**[A]** assumption · **[?]** unresolved · **[U]** could not be independently verified.

---

## 1. Sources consulted

| Source | What it gave | Notes |
|---|---|---|
| `https://data.elexon.co.uk/swagger/v1/swagger.json` (OpenAPI spec of the Insights API) | Endpoint list, query parameters, response schemas, endpoint descriptions | **[V]** reachable; this is the machine-readable form of the BMRS API docs. The docs web pages at `bmrs.elexon.co.uk/api-documentation/...` are a JavaScript SPA and cannot be scraped, so the OpenAPI spec was used instead. |
| `https://developer.data.elexon.co.uk/` | Dataset endpoint overview; statement that streaming endpoints are "minimal APIs … returning efficient JSON … no restrictions or limits on data return"; licence/terms pointers | **[D]** |
| Live API calls under `https://data.elexon.co.uk/bmrs/api/v1` | All **[V]** facts below | Unauthenticated; no API key required. |
| Nord Pool support page "About the N2EX Day Ahead Auction" (modified 26 Jul 2022) | N2EX day-ahead gate closure 09:50 GMT, results by 10:00 GMT | **[D]**, dated 2022 — current operating status in Jan 2026 **[U]** |
| EPEX SPOT press releases/brochures (search snippets only; the EPEX site returned HTTP 403 to automated fetches) | GB hourly day-ahead auction gate closure ~09:20 GMT (brochure snippet, partly garbled); GB half-hourly day-ahead auction 15:30 GMT (2018 press release, also cited by Modo docs) | **[U]** — could not open the primary pages. Treat as unverified. |
| Vercel docs (Python runtime, FastAPI, Functions limits) and Render docs ("Deploy for Free") | Platform compatibility, see `07-deployment-plan.md` | **[D]** |

## 2. Endpoint behaviour

### 2.1 FUELHH — actual generation

`GET /datasets/FUELHH/stream` (also non-stream `GET /datasets/FUELHH`).

- **[D]** Description: "half-hourly generation outturn (Generation By Fuel type) … aggregated by Fuel Type category and updated at
  30-minute intervals with **average MW values over 30 minutes** for each category." Includes `settlementDate`/`settlementPeriod`.
- **[D]** Query parameters: `publishDateTimeFrom`, `publishDateTimeTo`, `settlementDateFrom`, `settlementDateTo`
  (format exactly `yyyy-MM-dd`), `settlementPeriod[]`, `fuelType[]`. Settlement-date parameters cannot be combined with publish-date parameters.
- **[V]** `?settlementDateFrom=2026-01-01&settlementDateTo=2026-01-31&fuelType=WIND` → HTTP 200, 269,971 bytes, ~1.6 s, **1,488 rows**.
- **[V]** Row shape: `dataset, publishTime, startTime, settlementDate, settlementPeriod, fuelType, generation`
  (`generation` integer; nullable per OpenAPI schema; **0 nulls and 0 zeros observed** for January).
- **[V]** Response is sorted newest-first (descending `startTime`). Do not rely on order; sort explicitly.
- **[V]** `startTime` is UTC (`...Z`). Minutes ∈ {00, 30}. 1,488 distinct `startTime`s = 31 × 48, exactly one row per settlement period.
- **[V]** `generation` range in January: 1,695 – 17,805 (units: MW, see §4).
- **[V]** A malformed date (`2026-1-1`) → HTTP 400 with an RFC 9110 problem-details body naming the parameter.
- **[V]** `fuelType` filter works; `fuelType=WIND` returns only `WIND` (the unfiltered one-day feed returned 20 distinct fuel types including interconnectors — not used).
- **[V]** Wind is a single national `WIND` category (no onshore/offshore split in this dataset).

### 2.2 WINDFOR — forecast generation

`GET /datasets/WINDFOR/stream` (also non-stream, plus "opinionated" derivatives below).

- **[D]** Description: "wind generation forecast data. Specific publish time filters may be supplied, otherwise this will retrieve **the latest published forecast**."
- **[D]** The opinionated endpoints (`/forecast/generation/wind/...`) state the forecast is "for wind farms which are **visible to the ESO and have operational metering**" and
  "published by NGESO up to 8 times a day at 03:30, 05:30, 08:30, 10:30, 12:30, 16:30, 19:30 and 23:30" (time zone **not stated**; see §3.3).
- **[D]** Query parameters on the dataset endpoint: **only** `publishDateTimeFrom`, `publishDateTimeTo` (+ `format` on non-stream). **There is no `startTime`/delivery-date filter.**
  To retrieve forecasts for a delivery window one must filter on *publish* time and then filter client-side by `startTime`.
- **[D]** Opinionated endpoints (not planned for core use): `/forecast/generation/wind/history` (by `publishTime`), `/evolution` (by `startTime` — returns how the forecast for one target evolved),
  `/latest`, `/earliest`, `/peak`. `/evolution` could cross-validate our vintage reconstruction (open item U-7).
- **[V]** Row shape: `dataset, publishTime, startTime, generation` (integer, nullable per schema; 0 nulls and 0 zeros in the retrieved window).
- **[V]** **Historical revisions are preserved with their original `publishTime`.** Retrieving `publishDateTimeFrom=2025-12-27T00:00:00Z … publishDateTimeTo=2026-02-04T00:00:00Z`
  returned **22,776 rows = 312 distinct `publishTime` vintages × 73 rows**. A request over 2025-10-01 → 2026-02-01 returned 71,856 rows (publishTimes from 2025-10-01T03:30Z), so the archive reaches at least October 2025.
- **[V]** `startTime` is UTC and **hourly**: every one of 22,776 rows has minute = 00. **The forecast has half the temporal resolution of FUELHH.**
- **[V]** Each vintage is a 73-hour block: from 25.5 h *before* publish (back-cast of already-elapsed hours) to 66.5 h after.
  `startTime − publishTime` ranges −25.5 h … +66.5 h. Forecast rows with negative lead time exist; they can never be "day-ahead" information.
- **[V]** For delivery hour `startTime`, the number of vintages containing it is 8, 16, 24 or 32 (mostly 24 → ~3 days of 8 daily vintages).
- **[V]** 0 duplicate `(startTime, publishTime)` pairs in the retrieved window.
- **[V]** Unlike FUELHH, `/forecast/generation/wind/latest/stream` rows carry `settlementDate`/`settlementPeriod`; e.g. `startTime 01:00Z → settlementPeriod 3`, i.e. each hourly row is anchored on the settlement period that *begins* at `startTime`.

## 3. Time, timezone and publication schedule

### 3.1 Timestamps
- **[V]** All timestamps in both datasets are ISO-8601 UTC with `Z`, second precision. `settlementDate` is the **UK (Europe/London) local settlement date**.
- **[V]** In January Europe/London = UTC (GMT), so `startTime` date == `settlementDate` and settlement period *n* starts at `(n−1)×30 min` after 00:00Z. January contains **no** DST transition, so the date-boundary logic is trivial for this assignment — but the code must still be correct in general and is tested on clock-change days.
- **[V]** Clock-change behaviour of FUELHH (2025): `2025-03-30` → **46** periods (`startTime 2025-03-30T00:00Z … 22:30Z`); `2025-10-26` → **50** periods (`2025-10-25T23:00Z … 2025-10-26T23:30Z`). Settlement periods are numbered 1..46 / 1..50 and `startTime` is a UTC instant, so **UTC `startTime` is the safe join key** (never `settlementPeriod` alone, never naive local time).
- **[A]** Expected interval count for a delivery date = number of 30-min UTC instants within `[local midnight, next local midnight)`; 48 normally, 46/50 on clock-change days. January 2026 = 31 × 48 = **1,488** half-hours = **744** hourly forecast slots.

### 3.2 Delivery date vs decision date
- **[D/A]** Delivery date D (a London settlement date) is purchased in a day-ahead auction on **D−1**, with gate closure on D−1 at a clock time in Europe/London (see §3.4). The decision instant is therefore `(D−1) @ cutoff_time Europe/London → UTC`.

### 3.3 WINDFOR publication schedule (important — do not hardcode)
- **[V]** In the January window the publishTimes (UTC) are exactly: 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30, 22:30 (39 days × 8). The documented list (03:30, 05:30, 08:30, 10:30, 12:30, 16:30, 19:30, 23:30) is **exactly one hour later** than the observed UTC times, i.e. documentation appears to quote CET/Brussels-style clock times (**[?]** not stated).
- **[V]** In July 2025 the observed UTC publish times were 03:30, 05:30, 08:30, 12:54, 16:30, 19:30, 23:30 (7 vintages on the day sampled; one off-pattern) — i.e. **the UTC schedule differs between winter and summer and is not strictly regular**. Therefore the application must use the `publishTime` values from the data and never infer them from a nominal schedule.
- **[V]** Anomaly: on **2026-01-15** the 11:30Z vintage is **absent** and an off-schedule vintage exists at **12:25Z** (73 rows). Also on 2026-01-15 exactly four FUELHH settlement periods (SP 21–24, `startTime` 10:00–11:30Z) carry `publishTime` 12:25/12:26Z instead of the usual `startTime + 30 min` (lags of 145, 116, 86 and 56 min). Both anomalies coincide and look like a short upstream reporting delay on that day (**[?]** cause not documented). Good real-data regression case. Only these 4 of 1,488 rows deviate from the +30 min pattern.
- **[V]** FUELHH `publishTime = startTime + 30 min` for 1,484 of 1,488 rows (i.e. the half-hour's end), consistent with publication at interval end.

### 3.4 Day-ahead market cutoff research
The brief prohibits hard-coding an unsupported cutoff. What I could establish:

| Auction | Gate closure (London clock) | Evidence | Status |
|---|---|---|---|
| N2EX Day-Ahead (Nord Pool), hourly | **09:50 GMT** (results by 10:00 GMT) | Nord Pool support page, last modified 26 Jul 2022 | **[D]** (date caveat; whether N2EX DA was still operating in Jan 2026 is **[U]**) |
| EPEX SPOT GB Day-Ahead 60-min | ~**09:20** GMT (results 09:30) | Brochure/press-release snippets only; EPEX site blocked automated fetch | **[U]** |
| EPEX SPOT GB Day-Ahead 30-min | **15:30** GMT | 2018 EPEX press release (snippet) and Modo documentation page | **[U]**-ish (two secondary mentions) |
| EPEX GB Intraday auction 1 | 17:30 GMT, delivery next day | 2018 EPEX press release | **[U]** — intraday, not day-ahead |
| Post-Brexit | GB DA 60-min auction is no longer coupled with SDAC; interconnectors use explicit auctions | EPEX "focus GB" snippet | **[D]** |

**Consequence:** there is no single universally correct cutoff, and the *choice changes which WINDFOR vintage is eligible* because the 09:30Z vintage sits between 09:20 and 09:50
(see §6.3 for the measured effect). Plan: **default 09:50 Europe/London on D−1, configurable**, with presets 09:20 / 09:50 / 15:30 and free entry, and an explicit
"assumed availability lag" parameter (default 0). Final default needs user confirmation (see `08-risks-and-decisions.md`, D-1).

## 4. Units & definitions

- **[D]** FUELHH: "average MW values over 30 minutes" → **MW (average power over the half-hour)**. Energy per period = MW × 0.5 h = MWh.
- **[A]** WINDFOR unit is **MW** (the OpenAPI schema declares only `integer`; the magnitudes — 2,250–21,353 — are consistent with GB-wide MW and with FUELHH). Marked **[U]** formally.
- **[V]** The forecast mean ≈ 1.8 GW higher than outturn in January (see §6.2). **[?]** Cause unknown.

### Are the two datasets definitionally compatible? — Not proven. Treat as a headline caveat.
- **[D]** WINDFOR covers wind farms "visible to the ESO and with operational metering".
- **[D]** FUELHH is "generation outturn by fuel type" for Great Britain; the OpenAPI description does not state which assets are included (e.g. embedded wind, BM vs non-BM units). **[?]**
- **[A/hypothesis, unverified]** Possible contributors to the observed systematic over-forecast: different asset coverage between datasets; forecast representing available/potential output versus outturn after curtailment/constraint actions; forecast skill itself. **None of these has been tested.** The product must not attribute the bias to any cause.
- **Required UI/README wording:** "Measured differences may reflect differences in dataset scope as well as forecast performance."

## 5. Volume, limits, availability

- **[V]** January FUELHH ≈ 270 KB; WINDFOR over 2025-12-27 → 2026-02-04 ≈ 2.5 MB (≈ 22.8k rows). Whole-month, single-request streaming worked in ~2.4 s. A 4-month WINDFOR pull (8 MB) and 4-month FUELHH pull (1 MB) also succeeded in one request.
- **[D]** Stream endpoints: "no restrictions or limits on data return" (developer portal). Response codes documented: 200, 400, 429 (rate limit), 500.
- **[V]** No rate-limit headers were present in responses; I did not trigger a 429 (about 25 requests made). Real limits **[U]** → ingestion must retry on 429/5xx with back-off (`Retry-After` honoured if present) and be a one-off/offline job, not a per-request call.
- **[V]** January 2026 data (actuals and 8×/day forecast archive) is available now (system date 2026-10-25), >9 months after delivery.
- **[?]** Retention policy for the Insights API archive is not documented in what I read → pin a snapshot (see architecture).
- **[V]** No API key required. **Licence:** BMRS data licence requires attribution; the string commonly cited is "Contains BMRS data © Elexon Limited copyright and database right" **[U]** (the licence page is JS-rendered; confirm wording before publishing).

## 6. Exploratory, non-production observations (real data, throwaway calculation)

Method: for each delivery hour in January, take the latest WINDFOR vintage published at/before `D−1 @ cutoff` (UTC = London in January), step-hold across the two half-hours, error = actual − forecast. This is exploratory and **not** the production algorithm.

### 6.1 Coverage
Every delivery hour had an eligible forecast under every cutoff tested between 00:00 and 23:59 on D−1 *except* a 00:00-of-D−1 cutoff (682/744 hour-slots): so no unavailability arises at day-ahead cutoffs in this month. Unavailable-forecast handling is still required (configurable cutoffs, other months, API gaps) and is covered by tests using fixtures.

### 6.2 Metrics under the exploratory method (MW)

| Cutoff on D−1 | Lead time of selected vintage (h) | MAE | RMSE | Bias (actual − forecast) |
|---|---|---|---|---|
| 09:20 | 16.5 – 39.5 | 2,145 | 2,616 | −1,852 |
| 09:50 | 14.5 – 37.5 | 2,126 | 2,621 | −1,840 |
| 12:00 | 12.5 – 37.5 | 2,021 | 2,481 | −1,806 |
| 15:30 | 8.5 – 31.5 | 1,984 | 2,448 | −1,817 |
| 23:59 | 1.5 – 24.5 | 1,941 | 2,411 | −1,714 |

- **[V]** Bias is **negative at every horizon** (≈ −0.8 to −2.1 GW across 6-hour lead-time buckets): the forecast overstated outturn systematically in this month.
- **[V]** Later cutoffs → lower error, as expected; sensitivity is real but modest (MAE 1,941–2,145 MW).
- **[V]** The error differs little (±1 %) between hour-beginning / hour-centred / hour-ending alignment tests, so the data cannot discriminate which half-hours an hourly row represents (see assumption A-4).
- Within-hour variation of actual wind: mean |SP₁ − SP₂| = 217 MW (max 1,496 MW) — the step-hold approximation adds up to that much unavoidable "resolution error" to the half-hour comparison.

### 6.3 Why cutoff matters mechanically
The 09:30Z vintage is published 20 min *after* a 09:20 cutoff and 20 min *before* a 09:50 cutoff. Practical usability of a vintage 20 minutes after publication is unknown → the `availability_lag_minutes` parameter.

## 7. Verified / assumed / unresolved summary

### Verified facts [V]
1. Both datasets are reachable without authentication and contain complete January 2026 data (1,488 FUELHH WIND rows; 312 WINDFOR vintages × 73 hourly rows).
2. WINDFOR archive keeps all revisions with original `publishTime` (≥ Oct 2025 onward).
3. WINDFOR is **hourly**, FUELHH is **half-hourly**; both timestamps UTC.
4. WINDFOR has no delivery-time filter — retrieval is by publish-time window only.
5. Publication times seen in UTC vary seasonally and with exceptions (2026-01-15: 11:30Z missing, 12:25Z present).
6. No duplicate `(startTime, publishTime)` pairs; no null or zero generation values in the retrieved windows.
7. FUELHH has 46/50 settlement periods on DST change days.
8. Strong systematic negative bias (forecast > actual) in January regardless of cutoff.

### Assumptions [A]
- A-1 Units are MW for both datasets.
- A-2 `publishTime` is when the vintage became available to market participants (upper bound for what a trader could know; real-world latency ≥ 0).
- A-3 The latest vintage published ≤ cutoff is what a rational planner would use (no analyst-specific blends).
- A-4 An hourly WINDFOR row at `startTime` T represents average MW for `[T, T+60 min)` and therefore applies to both half-hours starting at T and T+30.
- A-5 Delivery date = Europe/London settlement date.
- A-6 FUELHH value for a `startTime` is final enough for evaluation (we see one value per startTime; later corrections, if any, are not observable).

### Unresolved [?]
- U-1 Exact asset coverage of FUELHH `WIND` vs WINDFOR (cause of the −1.8 GW bias).
- U-2 Whether WINDFOR hourly rows are hour-beginning or hour-ending (A-4).
- U-3 Time zone of the documented WINDFOR schedule and why summer UTC times differ.
- U-4 Authoritative gate-closure time of the intended auction (and whether N2EX/EPEX GB DA were the venues in Jan 2026).
- U-5 API rate limits and archive retention policy.
- U-6 Whether FUELHH values are later revised (the API exposes one `publishTime` per interval).
- U-7 Cross-check reconstruction vs `/forecast/generation/wind/evolution` (not yet called).
- U-8 Exact BMRS licence attribution text.
