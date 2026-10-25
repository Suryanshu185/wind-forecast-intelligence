# 06 — Testing Strategy

Principle: **test the analytical rules independently of Elexon availability**, with deterministic fixtures and hand-computed expectations. Real Elexon data is used for (a) a tiny verbatim excerpt fixture and (b) a regression test against the pinned snapshot. Anything fabricated is named `synthetic_*`, carries `"synthetic": true`, and is never displayed as real.

Tooling: backend **pytest** (+ pytest-cov, `pytest-httpx`/`respx` for mocked HTTP, `freezegun`/explicit clocks where needed; hypothesis optional P2). Frontend **Vitest + React Testing Library + @testing-library/user-event + MSW**; `jest-dom` matchers; `vitest-axe` (axe-core) for smoke accessibility checks (P1). Target: ≥ 90 % line coverage on `backend/app/domain`, meaningful (not vanity) coverage elsewhere.

## 1. Fixture strategy
| Fixture | Kind | Use |
|---|---|---|
| `synthetic_basic_day.json` | SYNTHETIC | Hand-built day with 4 vintages × several slots, values chosen so every expected number is calculable by hand. |
| `synthetic_missing.json` | SYNTHETIC | Gaps: missing actuals, slots with no eligible forecast, null generation, zero generation. |
| `synthetic_duplicates.json` | SYNTHETIC | Exact duplicate rows and conflicting `(start,publish)` rows with different MW. |
| `synthetic_dst_*.json` | SYNTHETIC | 2025-03-30 (46 SP) and 2025-10-26 (50 SP) calendar days; BST cutoffs. |
| `real_sample_windfor_20260115.json`, `real_sample_fuelhh_20260115.json` | **REAL (verbatim excerpt)** | Contains the actual 2026-01-15 anomalies (missing 11:30Z, extra 12:25Z vintage, late FUELHH SPs 21–24) to prove the code handles them. Provenance header in a sidecar `README`. |
| `data/snapshots/*` | **REAL (pinned)** | Regression test only (after approval D-3). |
| Frontend `msw` handlers | Synthetic API responses, typed against the schemas, labelled in file names | Component tests; never shown to users. |

Each synthetic file includes a top-level `_synthetic_notice` explaining it is invented test data.

## 2. Backend test matrix (maps to brief §8)

### Unit — `domain/calendar`
- Expected SP count: normal day 48; 2025-03-30 → 46; 2025-10-26 → 50; January total 1,488.
- `london_date(utc)` at 23:30Z/00:00Z boundaries in winter and in BST (e.g. 2025-06-30T23:00Z → 2025-07-01).
- Cutoff instants: 09:50 London in winter = 09:50Z; in summer = 08:50Z; nonexistent local time (01:30 on 2025-03-30) shifts forward; ambiguous (01:30 on 2025-10-26) → first occurrence.
- `days_before` 0/1/2 across month and year boundaries (delivery 2026-01-01 → decision 2025-12-31).

### Unit — `normalise`
- Parses ISO `Z` timestamps; rejects naive and offset strings; counts `rejected_rows`.
- `null` generation → missing (not 0); `0` preserved.
- Exact-duplicate collapse; conflicting duplicates under `min` and `exclude` policies; deterministic regardless of input order (parametrised over permutations).
- Off-grid forecast `startTime` (minute ≠ 0) excluded and counted.
- Negative values counted and kept.
- settlementDate vs London-date consistency counter.

### Unit — `selection`
- Latest eligible forecast chosen among multiple revisions.
- Forecast published **after** cutoff excluded even if later/better; published **exactly at** cutoff is included.
- Availability lag shifts eligibility (vintage at cutoff−10 min excluded when lag = 20).
- No eligible forecast → `FORECAST_UNAVAILABLE`, `forecast_mw = None` (assert not 0).
- Back-cast rows (`publish ≥ slot`) never eligible.
- Different cutoffs select different vintages for same interval (09:20 vs 09:50 around a 09:30 vintage — mirrors the real situation).
- Per-slot selection when a vintage lacks some slots.
- Hourly slot expands to both half-hours; `forecast_slot_start` correct.
- Equivalence: vectorised implementation == slow reference on randomised synthetic inputs (hypothesis P2; otherwise parametrised seeds).
- Not using "latest forecast currently available": explicit test where the latest-overall vintage differs and the metric would be different.

### Unit — `matching` / status
- Each status (MATCHED / FORECAST_UNAVAILABLE / ACTUAL_MISSING / BOTH_MISSING) produced correctly.
- Invariant: counts sum to expected; unexpected rows counted not matched.
- Matching by delivery interval, not publish time (adversarial fixture where publish-time ordering would mis-match).
- Zero actual vs missing actual distinguished (zero → matched with error = −F; missing → ACTUAL_MISSING).

### Unit — `metrics`
- Golden worked example (MAE 10, RMSE √150, bias −5, P90 17).
- Sign convention: actual > forecast ⇒ positive error; test over/under extremes ordering.
- Coverage denominators: expected from calendar even when data rows absent.
- `n = 0` ⇒ metrics `None`, coverage 0 %.
- Single matched interval; all-equal errors; large values (no overflow).
- Daily grouping across London midnight; DST day denominators 46/50.
- Histogram bin anchoring and counts sum to n; quantiles vs `numpy.percentile` linear.
- Top-k extremes ties broken by earlier time.
- Elevated-day rule with a day below 80 % coverage excluded.

### Unit — `scenarios`
- Buffer quantiles on a hand-computed error set; `max(0, …)` clipping; c monotonic (B50 ≤ B80 ≤ B90 ≤ B95).
- Rolling-origin uses only days ≤ D−2 (leakage test: mutate D−1 and D actuals and assert buffer unchanged).

### Integration
- Ingestion client with mocked HTTP: success; 400; 429 with `Retry-After`; 500 then success; timeout; truncated JSON; empty array; schema-violating rows → clear exception types; no partial snapshot written on failure (atomic write).
- Snapshot repository: manifest hash mismatch ⇒ refuses to start with explicit error; missing files; `is_synthetic` propagated.
- Incomplete datasets: forecast archive missing some days ⇒ coverage drops, API still 200 with partial flag.

### API (FastAPI `TestClient`)
- 200 shape validated against Pydantic response models; no `NaN`/`Infinity` in JSON (`allow_nan` check).
- 422 for: dates outside Jan 2026, `start > end`, bad `cutoff_time`, `days_before` out of range, unknown timezone.
- 404 unknown interval; 503/`DATA_UNAVAILABLE` when repository not loaded; error envelope shape.
- Cutoff change ⇒ response differs and echoes config.
- Provenance and `is_synthetic` always present; synthetic mode flagged.
- Determinism: same request twice ⇒ identical bytes.

### Regression (real snapshot; after D-3)
- Default config: `expected == 1488`, `matched == 1488`; MAE/RMSE/bias match the independent exploratory script within ±1 MW (09:50: 2,126 / 2,621 / −1,840). These golden numbers were produced by `research/probe_elexon.py`, an independent implementation, which is the point.
- 2026-01-15 anomalies handled: documented vintage at 12:25Z is selected for a 15:30-cutoff scenario only if eligible; FUELHH late rows present.

## 3. Frontend test matrix
| Area | Tests |
|---|---|
| Date restriction | Date inputs have `min=2026-01-01`/`max=2026-01-31`; selecting/typing outside is rejected or clamped with visible message; presets (whole month, a week) stay inside range; URL param outside range is corrected. |
| Metrics display | MAE/RMSE/Bias/P90 render with MW units, tooltip definitions, `n of expected` and coverage %; `null` metrics render "—" with explanation (not 0). |
| Chart | Renders actual & forecast series from MSW data; null points create gaps (assert dataset passed to chart has `null`, and legend shows "Forecast unavailable" entry); zero values rendered distinctly from missing; accessible table view mirrors data. |
| Interval inspection | Selecting an interval shows publish time, lead time, error with sign explanation, and the "why selected" text; keyboard (arrow keys) navigation. |
| Revision exploration | Panel lists vintages; eligible/selected/after-cutoff badges; post-cutoff rows labelled "not available at decision time". |
| Cutoff changes | Changing cutoff triggers a new request with the new params (MSW assertion), shows loading state, then updated metrics and selected publish time; URL updates. |
| States | Loading skeleton; error with retry (MSW 500 → retry succeeds); empty (no intervals); partial-data banner when coverage < 95 %; provenance badge shows SYNTHETIC vs REAL variants. |
| Decision view | Disclaimer always rendered; no £/volume text; buffer table values from response. |
| A11y smoke | axe: no critical violations on dashboard and methodology; focus order; labels on controls. |
| Methodology | Shows datasets, cutoff, tz, counts, retrieval time from `/meta` & `/data-quality`. |

## 4. Quality gates (run before each commit)
`ruff check` · `mypy` (backend, non-strict at start) · `pytest -q --cov` · `tsc --noEmit` · `eslint` · `vitest run` · secret scan (`git diff --cached | grep -iE "(key|token|secret|password)"` + manual review) · docker compose test profile (before M7 commit onward).

## 5. Not planned (explicit)
Load testing; cross-browser matrix beyond Chromium; visual regression. Optional P2: one Playwright smoke test on the deployed URL.
