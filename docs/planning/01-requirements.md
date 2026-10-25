# 01 — Requirements

Project: **UK Wind Forecast Intelligence Platform** — retrospective day-ahead wind-forecast evaluation for January 2026 (Elexon BMRS FUELHH vs WINDFOR).
Budget: 16 h implementation. Priorities: **P0** essential · **P1** important · **P2** optional (drop in reverse order).

## 1. Users and needs
| User | Need |
|---|---|
| Procurement analyst / trader | "What wind forecast could I see when the day-ahead decision was due, and how wrong was it?" |
| Procurement manager | "How much should I distrust the forecast? Which days were bad? What does uncertainty imply for planning?" |
| Hiring reviewer (Gridbricks) | Evidence of analytical rigour, engineering quality, product judgement. |

## 2. Scope boundaries
- IN: national GB wind generation; FUELHH (`fuelType = WIND`) and WINDFOR; delivery dates 2026-01-01…2026-01-31.
- OUT: demand, contracts, other generation, prices, other months, authentication/multi-user, live feeds, ML forecasting, any financial claims.
- The product describes itself as a **retrospective simulation**.

## 3. Functional requirements

### FR-A Forecast Explorer
| ID | Requirement | Pri |
|---|---|---|
| A1 | Delivery date range selectable only within January 2026 (UI min/max, API 422 outside). | P0 |
| A2 | Time-series of actual vs selected day-ahead forecast at 30-min resolution; units MW; London time shown (UTC also available). | P0 |
| A3 | Hover/keyboard inspection of an individual interval: actual, forecast, signed error (`actual − forecast`), forecast publication time, lead time, forecast slot (hourly) note. | P0 |
| A4 | "Why this forecast?" explanation per interval: cutoff instant used, number of eligible vintages, selected vintage and the rule. | P0 |
| A5 | Revision explorer: for the selected interval list/plot all vintages (publish time vs MW), marking eligible / selected / post-cutoff. | P1 |
| A6 | Unavailable forecast or missing actual rendered as a gap with distinct marker/legend entry — never drawn as zero. Zero MW rendered as a real value. | P0 |
| A7 | Loading, error (with retry), empty, and partial-data states consistent across all panels. | P0 |
| A8 | Cutoff controls (time, days-before, availability lag) with live recompute and visible effect on the results. | P0 |
| A9 | Zoom/brush on the time axis; day quick-select. | P1 |
| A10 | Optional uncertainty ribbon from historical error quantiles (labelled scenario). | P2 |

### FR-B Forecast accuracy analytics
| ID | Requirement | Pri |
|---|---|---|
| B1 | Cards: MAE, RMSE, Bias, P90 abs error (MW), each with definition tooltip and denominator ("n of expected"). | P0 |
| B2 | Interval coverage = matched / expected, with expected/observed/matched/missing counts. | P0 |
| B3 | Daily accuracy trend chart (MAE and bias per delivery date; coverage per day). | P0 |
| B4 | Error distribution histogram + quantiles. | P0 |
| B5 | Largest over-forecast and under-forecast intervals (top k) with click-through to the Explorer interval. | P0 |
| B6 | Missing / unmatched counts by category (forecast unavailable, actual missing, both). | P0 |
| B7 | Worst contiguous windows (e.g. 3 h). | P2 |
| B8 | Signed-error convention stated wherever errors appear: `error = actual − forecast`; negative = over-forecast. | P0 |

### FR-C Decision intelligence (optional view)
| ID | Requirement | Pri |
|---|---|---|
| C1 | Under-delivery buffers at 50/80/90/95 % from historical errors, labelled analytical scenarios. | P1 |
| C2 | Elevated-error days and error by hour of day. | P1 |
| C3 | Plain-language implications panel (what a buffer means; what the data cannot say). Static text templated from computed numbers, no fabricated claims. | P1 |
| C4 | Rolling-origin calibration of buffers. | P2 |
| C5 | Prominent disclaimer; no shortfall/volume/cost/profit outputs. | P0 (if C exists) |

### FR-D Data quality & methodology
| ID | Requirement | Pri |
|---|---|---|
| D1 | Methodology page/panel: source datasets (with official links), date range, cutoff + timezone, expected/observed/matched/missing counts, retrieval timestamp, assumptions, limitations. | P0 |
| D2 | Persistent provenance badge: "Real Elexon data (snapshot retrieved …)" or "SYNTHETIC DEVELOPMENT FIXTURE". | P0 |
| D3 | Anomaly list (e.g. missing/off-schedule vintages, late-published actuals, duplicates/conflicts). | P1 |
| D4 | Dataset-scope caveat banner (FUELHH vs WINDFOR). | P0 |

## 4. Analytical correctness requirements (all P0)
- AC-1 For each delivery interval, only forecasts with `publishTime ≤ cutoff` are eligible; the latest is selected; none → unavailable.
- AC-2 Matching to actuals by delivery interval start (UTC), never by publish time.
- AC-3 Deterministic duplicate/conflict rule; counters surfaced.
- AC-4 No imputation; zero ≠ missing; missing disclosed in coverage.
- AC-5 Cutoff configurable; delivery date vs decision date distinguished; timezone Europe/London with DST-correct computation.
- AC-6 Metric formulas and denominators exactly as `05-analytics-methodology.md`.
- AC-7 Results never use the "latest forecast available today" for historical decisions.

## 5. Non-functional requirements
| ID | Requirement | Pri |
|---|---|---|
| N1 | Tech: React + TypeScript; Python + FastAPI; pandas/NumPy; Docker + Compose. | P0 |
| N2 | Backend tests (pytest) and frontend tests (Vitest + React Testing Library) — see `06-testing-strategy.md`. | P0 |
| N3 | Public GitHub repo with anonymous name; public deployed URL; README per brief. | P0 |
| N4 | API response time < 500 ms for a full-month analysis from warm cache; first meaningful paint < 3 s on broadband after warm service. | P1 |
| N5 | Responsive (≥ 360 px) and keyboard accessible; WCAG 2.1 AA contrast; charts have text alternatives (data table toggle). | P1 |
| N6 | Deterministic: same snapshot + same config → identical numbers. | P0 |
| N7 | No secrets in repo; `.env.example` only; no API key needed. | P0 |
| N8 | Structured logging; typed request/response schemas (Pydantic v2); OpenAPI docs at `/docs`. | P1 |
| N9 | Elexon attribution/licence notice shown in app footer + README. | P0 |
| N10 | Works offline from pinned snapshot; live refresh is a separate CLI/command with retries/back-off. | P0 |
| N11 | Static typing: `mypy`/`pyright` (backend, light) and `tsc --strict` (frontend); lint: ruff, eslint. | P1 |

## 6. Deliverables (from brief)
Working app · Docker-based local dev · automated tests · public repo · public deployment · README (all required sections incl. AI-usage disclosure of Kiro / ChatGPT where applicable) · ≤10-min unlisted YouTube demo (Part 1 customer pitch ≤5 min; Part 2 technical review ≤5 min). The demo recording and upload are performed by the user.

## 7. Acceptance criteria (summary)
1. With default config, `/analysis` reports expected = 1,488 and reproduces the independently computed exploratory values (MAE 2,126 / RMSE 2,621 / bias −1,840 MW at 09:50 cutoff, to ±1 MW) — a regression test using the pinned real snapshot.
2. Changing the cutoff changes the selected vintage (publish time) for affected intervals and the metrics, and the UI says so.
3. Removing an eligible vintage (fixture) yields "unavailable", coverage < 100 %, no zero-fill.
4. All tests green in CI-like local run (`docker compose run`), app runs via `docker compose up`.
5. Every number shown in the UI traces to a backend response; no hard-coded result values.
