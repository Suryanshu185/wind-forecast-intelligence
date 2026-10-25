# 02 — Architecture & Design

## 1. Principles
1. **Correctness first, pure core.** The analytical logic (normalise → select → match → metrics) is pure functions over typed in-memory data; no I/O, no framework imports. It is tested without the network.
2. **Offline-deterministic by default.** A pinned snapshot of real January 2026 Elexon data is the default data source; live ingestion is a separate, explicit command. The deployed app never depends on Elexon availability.
3. **Boring architecture.** One backend service, one SPA. No database, queue, cache server or microservices — the full dataset is ~24k rows (~3 MB raw).
4. **Single deployable.** Production image serves the built React app and the API from one origin (no CORS, one URL).
5. **Provenance everywhere.** Every response carries data provenance and configuration echo.

## 2. System context & data flow
```
            (offline / on demand, CLI)                       (runtime)
 Elexon Insights API ──► ingestion ──► normalise ──► snapshot files ──► repository (in-memory) ──► analytics core ──► FastAPI ──► React SPA
 FUELHH, WINDFOR        client+retry   validate       data/snapshots/    loaded once at startup    select/match/        /api/v1      charts, tables,
                                       dedupe         + manifest.json    (immutable)               metrics/scenarios                 methodology
```
- Ingestion (`python -m app.cli ingest`): two streaming requests (FUELHH Jan; WINDFOR by `publishDateTime` 2025-12-27 → 2026-02-04), raw → normalised CSV.gz + `manifest.json` (retrieval timestamp, request URLs, row counts, SHA-256, `is_synthetic: false`). The extended publish window covers cutoffs up to D−3 and the post-delivery vintages shown in the revision explorer.
- Runtime: `Repository` loads the snapshot, verifies the manifest hash, exposes read-only DataFrames. Requests build an `AnalysisConfig`, run the core, return Pydantic models. Results of the heavy path are memoised by `(config hash, dataset hash)` with `functools.lru_cache` (small, bounded).

## 3. Repository layout (monorepo)
```
.
├── README.md
├── LICENSE                       # TBD (decision D-11)
├── .env.example  .gitignore  .dockerignore
├── docker-compose.yml            # backend, frontend(dev), tests profiles
├── Dockerfile                    # multi-stage prod image (frontend build → python runtime)
├── docs/
│   ├── planning/                 # this folder
│   └── images/                   # README screenshots (added at the end)
├── data/
│   └── snapshots/                # (pending approval) real Jan-2026 snapshot + manifest.json
├── backend/
│   ├── pyproject.toml            # uv-managed; pinned deps
│   ├── app/
│   │   ├── main.py               # FastAPI factory, static mount, lifespan (load snapshot)
│   │   ├── config.py             # pydantic-settings; env → Settings
│   │   ├── logging.py
│   │   ├── api/                  # routers: meta, analysis, intervals, uncertainty, data_quality, health
│   │   ├── schemas/              # Pydantic request/response models (API contract)
│   │   ├── services/             # AnalysisService: orchestrates repo + core, caching
│   │   ├── domain/               # PURE core
│   │   │   ├── calendar.py       # London dates, expected SPs, cutoff instants (zoneinfo)
│   │   │   ├── models.py         # frozen dataclasses: ActualRecord, ForecastRecord, SelectedForecast…
│   │   │   ├── normalise.py      # parsing, dedupe/conflict policy, counters
│   │   │   ├── selection.py      # vintage selection (§3 of methodology)
│   │   │   ├── matching.py       # SP↔slot expansion, status taxonomy
│   │   │   ├── metrics.py        # MAE/RMSE/bias/P90/coverage, daily, histogram, extremes
│   │   │   └── scenarios.py      # buffers, bands, breakdowns, rolling-origin
│   │   ├── ingestion/            # elexon_client.py (httpx, retry), snapshot_writer.py, synthetic.py
│   │   ├── repository/           # SnapshotRepository, SyntheticRepository (same Protocol)
│   │   └── cli.py                # ingest | verify-snapshot | make-synthetic
│   └── tests/
│       ├── unit/ (calendar, normalise, selection, metrics, scenarios)
│       ├── api/ (TestClient: validation, error handling, response schema)
│       ├── integration/ (ingestion client with mocked HTTP; snapshot repo)
│       ├── regression/ (pinned real snapshot → golden numbers)
│       └── fixtures/ (synthetic_*.json — labelled; real_sample_*.json — tiny verbatim excerpts)
└── frontend/
    ├── package.json  vite.config.ts  tsconfig.json  tailwind config
    └── src/
        ├── main.tsx  App.tsx
        ├── api/ (client.ts, hooks via TanStack Query, generated-or-hand types)
        ├── types/ (domain types mirroring API)
        ├── lib/ (format.ts, time.ts, units.ts, constants.ts [JAN_2026 bounds])
        ├── components/ui/ (shadcn primitives: button, card, tooltip, tabs, select, popover…)
        ├── components/ (MetricCard, StatusBanner, ProvenanceBadge, EmptyState, ErrorState, Skeletons, InfoTooltip)
        ├── features/
        │   ├── controls/ (DateRange, CutoffControls)
        │   ├── explorer/ (ForecastChart, IntervalInspector, RevisionPanel)
        │   ├── accuracy/ (MetricsGrid, DailyTrendChart, ErrorHistogram, ExtremesTable, CoverageBreakdown)
        │   ├── decision/ (BufferTable, HourOfDayChart, ImplicationsPanel)
        │   └── methodology/ (MethodologyPage, DataQualityPanel, Glossary)
        └── test/ (setup, msw handlers, fixtures)
```

## 4. Key backend design decisions
| Decision | Choice | Why / alternative rejected |
|---|---|---|
| Data store | In-memory pandas frames from snapshot | ~24k rows. SQLite/Postgres add ops cost, no benefit. |
| Time handling | UTC `datetime`/`pandas.Timestamp(tz=UTC)`; `zoneinfo` for London | Avoids naive-time bugs; join key is UTC start. |
| Core purity | `domain/` imports only stdlib, numpy, pandas | Testable without FastAPI/network. |
| Selection implementation | Vectorised: merge SP expansion with forecasts, filter `publish ≤ cutoff`, `sort_values(['slot','publish'])`, `groupby('slot').tail(1)`; mirrored by a slow, obviously-correct reference implementation used in a property test (hypothesis, if time) | Speed + verifiable equivalence. |
| API style | REST, versioned `/api/v1`, GET with query params (idempotent, cacheable) | Config is small; shareable URLs reflect UI state. |
| Validation | Pydantic v2 request models via `Depends`; 422 field errors; custom 4xx/5xx error envelope `{code, message, details}` | Consistent frontend handling. |
| Provenance | `ProvenanceInfo{mode, retrieved_at, sha256, is_synthetic, sources[]}` embedded in every analytic response | Brief §4D, §2 (synthetic must be labelled). |
| Live mode | Optional `DATA_SOURCE_MODE=live` uses same ingestion code at startup with timeout/retry, falling back with explicit error (never silently to synthetic) | Resilience without hidden substitution. |
| Synthetic data | `ingestion/synthetic.py` generates deterministic fixtures; manifest `is_synthetic: true`; UI badge turns amber/red | Honest dev/test data. |
| Dependency mgmt | `uv` (installed locally) with lockfile; Docker uses `uv sync --frozen` | Reproducible, fast; disk-light vs pip caches. |

## 5. API surface (v1, detailed schemas in implementation phase)
Common query params (`AnalysisConfig`): `delivery_start`, `delivery_end`, `cutoff_time` (HH:MM), `days_before`, `availability_lag_minutes`, `timezone` (default Europe/London).

| Method & path | Returns |
|---|---|
| `GET /api/v1/health` | liveness + dataset loaded flag |
| `GET /api/v1/meta` | permitted window, defaults, presets for cutoff, provenance, dataset descriptions, attribution text, version |
| `GET /api/v1/analysis/summary` | echoed config; counts (§3.1); metrics; daily metrics; histogram + quantiles; extremes; provenance |
| `GET /api/v1/analysis/intervals` | per-SP rows: `start_utc`, `start_local`, `actual_mw|null`, `forecast_mw|null`, `error_mw|null`, `status`, `forecast_published_at|null`, `lead_time_h|null`, `forecast_slot_start` (paginated by date range; ≤ 1,488 rows/month) |
| `GET /api/v1/intervals/{start_utc}/revisions` | all vintages for the slot with eligible/selected flags + actual + explanation text fields |
| `GET /api/v1/uncertainty/scenarios` | buffers per confidence, bands, hour-of-day breakdown, elevated-error days, optional rolling-origin table; includes disclaimer string |
| `GET /api/v1/data-quality` | §6 of methodology |
| `GET /docs`, `/openapi.json` | FastAPI interactive docs |

Error envelope: `{"error": {"code": "VALIDATION_ERROR|OUT_OF_RANGE|DATA_UNAVAILABLE|INTERNAL", "message": "...", "details": [...]}}`.
Numbers are JSON numbers or `null` (never `NaN`/`Infinity`).

## 6. Frontend architecture
- **Stack:** Vite + React 18 + TypeScript (strict) · Tailwind CSS · shadcn/ui (Radix primitives for accessible dialogs, tooltips, tabs, selects) · Recharts for charts · TanStack Query for server state · React Router (2–3 routes: Dashboard, Methodology) · Vitest + React Testing Library + MSW.
- **State:** URL search params are the source of truth for the analysis config (date range, cutoff, lag) → shareable links, back-button friendly; TanStack Query caches responses by config. Local UI state (selected interval, panel tabs) via `useState`/small context. No Redux.
- **Page composition:** `Header(provenance badge, nav)` → `ControlBar(date range, cutoff, lag)` → `DatasetScopeBanner` → tabs: **Explorer** | **Accuracy** | **Decision** (optional) → `Methodology` route → `Footer(attribution)`.
- **Charts:** Recharts `ComposedChart` with two `Line`s (actual, forecast) using `connectNulls={false}` so gaps are real; custom tooltip (all values + publish time + error); `ReferenceArea` shading for unavailable-forecast ranges; `Brush` for zoom; a "view as table" toggle for accessibility; colour-blind-safe palette with non-colour cues (dash pattern/markers). 1,488 points: Recharts is sufficient; if jank appears, downsample for display only (min/max decimation) with metrics unaffected.
- **Reusable states:** `<AsyncPanel query={…}>` renders skeleton / error+retry / empty / partial-data banner / content consistently for every panel.
- **Design system:** dark navy surface (`#0B1220` base, raised `#111A2E`/`#17233B`), restrained accent (teal/cyan for actual, amber for forecast; semantic red/green reserved for over/under-forecast with icons + labels, not colour alone), type: Inter (UI) + JetBrains Mono / tabular-nums for figures; 8-px spacing grid; subtle borders instead of heavy shadows. Light theme out of scope.
- **Typing:** `types/` mirrors backend schemas by hand (or `openapi-typescript` generated from `/openapi.json` if time permits — P2).
- **Accessibility:** semantic landmarks, focus-visible styles, keyboard-operable controls and interval stepping (←/→ on chart focus), tooltips accessible on focus, `aria-live` for load/error, contrast ≥ 4.5:1.

## 7. Docker & environments
- `docker-compose.yml`: `backend` (uvicorn --reload, mounts source), `frontend` (Vite dev server, proxy `/api` → backend), `tests` profile running `pytest` and `vitest` in containers. One-command start: `docker compose up`.
- Production `Dockerfile` (multi-stage): `node:20-slim` builds `frontend/dist` → `python:3.12-slim` installs backend deps via uv, copies snapshot + dist, runs `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. FastAPI serves `/api/*` and static SPA with history fallback.
- Config: environment variables via `pydantic-settings`; defaults safe; `.env.example` documents all.
- **Local constraint:** the dev machine currently has ~920 MiB free disk (`df`), which is tight for `node_modules` (~300–500 MB), a Python venv with pandas/numpy (~250 MB), and Docker images/layers. Mitigations: use `uv` cache pruning, shared Docker layers, `npm ci --omit=optional`, delete build caches regularly; ask the user to free disk (≥ 5 GB recommended) before M0. See risk R-6.

## 8. Security & operations notes
- Public read-only API over public data; no authentication by design (state in README: *no auth, rate limiting via platform only; contains no user data*). Add per-IP rate limiting (`slowapi`) only if time permits (P2).
- Input validation on all query params; CORS restricted to configured origins in dev, same-origin in prod.
- Dependency versions pinned via lockfiles; Dependabot not needed.
- Structured JSON logs with request id; no PII.
- Elexon attribution displayed (N9).

## 9. Snapshot vs live — recommended approach (decision D-3)
Commit a **pinned real snapshot** (measured: ~135 KB as gzipped CSV — 22,776 WINDFOR rows ≈ 121 KB, 1,488 FUELHH rows ≈ 15 KB) under `data/snapshots/` with `manifest.json`. Reasons: (a) deterministic tests and regression numbers, (b) deployment independent of Elexon uptime/rate limits and of the Insights archive retention (U-5), (c) fast cold starts. Cost: repo contains third-party data → licence attribution included; `.gitignore` already leaves the directory un-ignored while excluding other generated data. If you prefer no data in git, fallback: snapshot generated at Docker build time via `ingest` (adds build-time network dependency and risk).
