# 03 — Prioritised Implementation Task List (16 h budget)

Assumes the planning phase is **not** counted against the 16 h (decision D-9). Estimates are for focused implementation including tests.
Rule: *vertical slice first* — a thin end-to-end path (snapshot → selection → metrics → API → chart) before breadth or polish.
Commit at the end of each milestone after `git status`/`git diff` review and passing tests (see Git workflow in `02`/brief §9).

| # | Milestone | Hours | Cum. | Pri | Exit criteria |
|---|---|---|---|---|---|
| M0 | Scaffolding & tooling | 0.75 | 0.75 | P0 | `backend/` (uv, FastAPI hello, pytest, ruff) and `frontend/` (Vite+TS+Tailwind+shadcn init, Vitest) run locally; compose skeleton; CI-less `make test` equivalents documented. Disk space check done. |
| M1 | Ingestion, normalisation, snapshot | 1.75 | 2.5 | P0 | `elexon_client` (httpx, retry/back-off, 429/5xx), `normalise.py` incl. duplicate/conflict policy and counters; `cli ingest` produces snapshot + manifest; `SnapshotRepository` loads & hash-verifies; tests with mocked HTTP + real-excerpt fixtures. **Snapshot commit only after approval (D-3).** |
| M2 | Analytical core (TDD) | 2.25 | 4.75 | P0 | `calendar.py` (DST-correct cutoffs, expected SP counts), `selection.py`, `matching.py`, `metrics.py` with golden tests (worked example §4.1), missing/zero/duplicate/DST/boundary tests; regression test reproduces the exploratory numbers from the real snapshot. |
| M3 | Backend API | 1.5 | 6.25 | P0 | `/meta`, `/analysis/summary`, `/analysis/intervals`, `/intervals/{ts}/revisions`, `/data-quality`, `/health`; Pydantic schemas; validation (422 outside Jan 2026); error envelope; API tests incl. failure paths. Static SPA mount. |
| M4 | Frontend foundation + Explorer | 2.75 | 9.0 | P0 | Design tokens, layout, control bar (URL-state), API client + TanStack Query, `AsyncPanel` states, ForecastChart (gaps, tooltip, brush), IntervalInspector with "why this forecast", provenance badge, scope banner. Component tests for date restriction, states, cutoff change. |
| M5 | Accuracy analytics UI + Methodology | 1.5 | 10.5 | P0 | Metric cards with tooltips/denominators, coverage breakdown, daily trend, histogram, extremes table (click-through), methodology/data-quality page. Tests for metrics display and missing-data states. |
| M6 | Revision explorer + Decision intelligence | 1.0 | 11.5 | P1 | `RevisionPanel` (P1); `/uncertainty/scenarios`; buffer table, hour-of-day chart, elevated days, disclaimers (P1). Rolling-origin (P2) only if ahead. |
| M7 | Docker, deployment | 1.25 | 12.75 | P0 | `docker compose up` works end-to-end; test profile runs both suites; prod Dockerfile; deployed publicly (**after your approval**); smoke test on public URL. |
| M8 | README, screenshots, a11y/polish | 1.25 | 14.0 | P0 | README per brief (incl. AI-usage disclosure), screenshots, responsive pass at 360/768/1280, keyboard + contrast check, Lighthouse a11y run, final lint/type/test. |
| M9 | Demo prep | 1.0 | 15.0 | P0 | Script for two ≤5-min parts, dry run, talking points on methodology; (recording/upload done by you). |
| — | Contingency | 1.0 | 16.0 | — | Debugging, deployment surprises. |

## Feature priority & cut order
**Must ship (P0):** vintage selection + cutoff config; actual-vs-forecast chart with gaps; interval inspector with "why"; MAE/RMSE/bias/P90/coverage with denominators; daily trend; histogram; extremes; missing/unmatched counts; methodology/data-quality/provenance; Jan-2026 restriction; loading/error/empty/partial states; backend+frontend tests; Docker; deployment; README; demo.

**Should ship (P1):** revision explorer; decision-intelligence buffers + hour-of-day + elevated days + implications panel; zoom/brush; table view of chart; anomaly list; URL-shareable state; response-time hygiene.

**Nice (P2):** rolling-origin calibration; uncertainty ribbon on chart; worst contiguous windows; nMAE; OpenAPI-generated TS types; hypothesis property test of selection; rate limiting; Playwright smoke test.

**Cut order if time is short (first dropped → last):**
1. Rolling-origin calibration → 2. Uncertainty ribbon → 3. Worst-window analysis → 4. OpenAPI-generated types / property tests / Playwright → 5. Hour-of-day and lead-time breakdowns → 6. Brush/zoom (keep day quick-select) → 7. Revision explorer *chart* (keep table) → 8. Decision-intelligence view (keep only buffer table + disclaimer) → never cut: correctness tests, coverage disclosure, provenance, README, deployment.

## Task breakdown (checkable)
### M0
- [ ] Verify free disk ≥ 3 GB (current ≈ 0.9 GB) and Docker Desktop disk budget
- [ ] `uv init` backend; add fastapi, uvicorn, pydantic-settings, pandas, numpy, httpx; dev: pytest, pytest-cov, ruff, mypy, respx/`pytest-httpx`
- [ ] `npm create vite` (React-TS); tailwind; shadcn init; recharts; @tanstack/react-query; react-router; vitest, RTL, msw, jest-dom
- [ ] docker-compose skeleton; `.dockerignore`
### M1
- [ ] `config.py`; `logging.py`
- [ ] `models.py` frozen dataclasses
- [ ] `elexon_client.py`: stream GET, `publishDateTime*`/`settlementDate*` params, retry/back-off honouring `Retry-After`, timeout, schema validation of rows
- [ ] `normalise.py`: parse UTC, nulls, dedupe/conflict, counters
- [ ] `snapshot_writer.py` + `manifest.json` (+ SHA-256) ; `SnapshotRepository`
- [ ] `synthetic.py` (deterministic, flagged)
- [ ] tests: parsing, malformed rows, dedupe, shuffled order, HTTP 429/500 retry, truncated/partial response
### M2
- [ ] `calendar.py`: london_date, expected_sps(D), cutoff_instant(D, time, days_before) incl. gap/overlap
- [ ] `selection.py` + reference slow implementation
- [ ] `matching.py` status taxonomy + counters + invariants
- [ ] `metrics.py` MAE/RMSE/bias/P90/coverage, daily, histogram, extremes
- [ ] golden + edge tests (see `06`)
- [ ] regression test vs. real snapshot (after D-3)
### M3
- [ ] schemas; routers; dependency for config validation (Jan-2026 window)
- [ ] error handlers; OpenAPI examples
- [ ] service layer + LRU cache
- [ ] API tests (happy, 422, 404 interval, data unavailable 503, response schema, no NaN)
### M4–M6
- [ ] tokens & layout; `AsyncPanel`; `ControlBar` with URL state; `ForecastChart`; `IntervalInspector`; `MetricCard`; charts; tables; `RevisionPanel`; Decision view; Methodology page
- [ ] component tests per `06`
### M7–M9
- [ ] compose dev/test profiles; prod Dockerfile; smoke script
- [ ] deployment (approval required) + public smoke test
- [ ] README, screenshots, a11y, Lighthouse, final checks, pre-publication checklist (brief §10)
- [ ] demo script

## Early de-risking spikes (inside M0/M1, < 30 min total)
1. Confirm `uv`+FastAPI+pandas image size and cold-start time locally.
2. After approval: throwaway deploy of the hello-world Docker image to the chosen host to confirm the pipeline (not the real app) — avoids last-hour surprises.
