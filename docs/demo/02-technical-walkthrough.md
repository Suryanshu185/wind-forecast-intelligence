# Part 2 — Technical review (target 4:30, hard limit 5:00)

Audience: engineers / hiring panel. Show code and tests, not slides. Editor + terminal side by side.

| Time | Show | Say |
|---|---|---|
| 0:00–0:35 | README architecture diagram, repo tree | "FastAPI + pandas/NumPy backend, React/TypeScript frontend, one Docker image. No database: the whole dataset is ~24k rows, so a pinned, SHA-256-verified snapshot of real Elexon data is the default source. That makes tests deterministic and the deployed app independent of Elexon's uptime. The analytical core in `domain/` has no I/O or framework imports." |
| 0:35–1:15 | `docs/planning/04-data-research-notes.md` (§2, §9, §10) | "Before writing analytics I probed the live API and recorded verified facts vs assumptions vs open questions. Key findings: WINDFOR has no delivery-time filter, only publish time; it keeps every revision; it is hourly while FUELHH is half-hourly. Hour alignment is not documented anywhere I could reach, so it's a labelled assumption with a sensitivity switch — I did **not** pick it by lowest error. And the 1.8 GW bias: I traced it with an independent BMRS series — units, duplicates, cutoff, vintages and alignment were ruled out; the evidence points at dataset scope. No correction applied." |
| 1:15–2:10 | `domain/selection.py` | "The core rule: eligible = published ≤ cutoff − lag **and** before the hour described; pick the latest; otherwise `Selection` with `forecast_mw=None` — never zero. Conflicting duplicates aren't resolved by picking a value: they're removed, preserved and counted, and policies `exclude`/`strict` define what an affected interval does." Briefly show `calendar.cutoff_instant`: "UTC internally, `zoneinfo` for London; documented gap/overlap behaviour; expected counts 46/48/50 come from the calendar, not the data." |
| 2:10–3:10 | Terminal: `uv run pytest -q` then `-k oracle` | "242 backend tests: hand-computed golden examples, an independent brute-force oracle on random inputs, DST days, zero-vs-missing, shuffled input order, mocked HTTP failures (429 Retry-After, 5xx, timeout, truncated JSON), tampered snapshots. The regression test runs the production code on the real snapshot and must reproduce the MAE/RMSE/bias that my **separate stdlib probe script** printed — for five cutoffs, within 1 MW." Show `tests/regression/test_real_snapshot_analysis.py` PROBE table. |
| 3:10–3:50 | API: `/docs`, one curl with cutoff change, a 422 | "Typed Pydantic contract, one error envelope. Dates outside January 2026 → `422 OUT_OF_RANGE`. `/intervals/{ts}/revisions` returns every vintage with eligible/selected flags and an explanation. If the dataset fails to load: `/health` says degraded and endpoints return 503 — no silent fallback to other data." |
| 3:50–4:25 | Frontend: URL state, then `npm test` | "All analysis settings live in the URL, so any view is shareable; out-of-range values are sanitised. Missing values stay `null` end-to-end — charts break the line and hatch the gap. 41 Vitest tests cover date restriction, metric display, gaps vs zero, revision exploration, cutoff changes, loading/error/empty states." |
| 4:25–4:55 | Dockerfile, `render.yaml`, README limitations | "Multi-stage Docker image, non-root, serves API + SPA with a CSP. Render blueprint verified against the current spec; free tier spins down after 15 min so the UI explains a slow first load. **Honest status:** Docker Desktop's engine would not start on my machine (disk nearly full), so I verified the image layout by simulation and documented that the compose commands still need one run on a healthy host." |

## Questions to be ready for
- *Why not interpolate the hourly forecast to half-hours?* It would fabricate precision; the native hourly view is provided instead.
- *Why snapshot rather than call Elexon live?* Determinism, availability, and archive-retention risk; live ingestion is an explicit CLI with retry/back-off and atomic writes.
- *What would you do next?* Confirm the gate-closure time and WINDFOR alignment with Elexon/NESO; extend to other months (DST code is already tested); multi-month calibration of buffers.

## Pre-recording checklist
- [ ] Run all gates once beforehand so the terminal output is warm and short.
- [ ] Hide personal paths (shorten the shell prompt), no account names visible.
- [ ] Total under 5:00; combined with Part 1 under 10:00.
