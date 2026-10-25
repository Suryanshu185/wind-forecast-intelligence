# 08 — Risk Register & Decisions Requiring Confirmation

## 1. Decisions needing your confirmation

| ID | Decision | Options | Recommendation | Why it matters |
|---|---|---|---|---|
| **D-1** | Default decision cutoff | 09:20 / **09:50** / 15:30 / other, London time on D−1 | **09:50 Europe/London on D−1**, configurable, presets for 09:20 & 15:30, sensitivity shown in UI | Only 09:50 (N2EX, Nord Pool page, 2022) has a primary-source quote; EPEX 09:20/15:30 are unverified. The 09:30Z WINDFOR vintage falls between 09:20 and 09:50, so the choice changes results (MAE 2,145 vs 2,126 MW exploratory). |
| **D-2** | Comparison resolution | (a) 30-min SP level, hourly forecast step-held to both half-hours; (b) native hourly (mean of 2 SPs) | **(a)** for display and headline metrics (matches the brief's 30-min framing and 1,488 expected intervals), with (b) as an optional toggle if time permits | Step-hold makes adjacent errors dependent and slightly overstates nominal sample size; disclosed. |
| **D-3** | Commit a pinned real data snapshot (~135 KB) to the repo | Yes / No (fetch at build time) | **Yes** | Deterministic tests, offline Docker, deployment independent of Elexon. Data is reused with BMRS attribution. Needs your OK since it puts third-party data in the public repo. |
| **D-4** | Deployment platform | A Render Docker (recommended) / B Vercel / C split | **A**, spike early; fall back to B | Cold-start vs fidelity trade-off (see `07`). Requires your account/approval. |
| **D-5** | Availability-lag parameter | Include (default 0) / omit | **Include** | `publishTime` may not equal when a trader could act; lets the user test sensitivity. |
| **D-6** | Git author identity | Your global identity / anonymous placeholder | **Anonymous placeholder** (see below) | Public repo must be non-identifying; rewriting history later is prohibited. |
| **D-7** | Conflict policy default | `min` (conservative) / `exclude` | **`min`** | No conflicts exist in real January data, so impact is nil here; matters for rule completeness. |
| **D-8** | Repository name | see §3 | `fennel-ridge-q7k3` | Anonymous & random; availability on GitHub **unverified**. |
| **D-9** | Does planning time count toward the 16 h? | Yes / No | Assume **No** (implementation clock starts on approval) | Plan allocates exactly 16.0 h to implementation. |
| **D-10** | Scope of Decision view | Full P1 view / minimal buffer table | **Full P1**, cut per `03` if behind | Differentiator, but risk of over-claiming; wording is controlled. |
| **D-11** | Licence file | MIT (author "Contributors") / none | **MIT**, no personal name | Public repo; anonymous. |
| **D-12** | Frontend UI stack | Tailwind + shadcn/ui + Recharts + TanStack Query | **Yes** | Fits the brief's suggestions and the time budget. |
| **D-13** | Free disk space | Free ≥ 5 GB before M0 | **Required** | Only ~0.9 GiB free now (see R-6). |

### About D-6 (done during this phase)
Your global git config has a name and e-mail configured (values not echoed here). To avoid binding your real identity to a repository that will become public, the **initial commit was created with a one-off anonymous placeholder author** (`anon <anon@example.invalid>`) passed via `git -c …` on that command only. Your git configuration (global or local) was not modified. Later commits in this repo need the same treatment unless you tell me otherwise; if you prefer your own identity, tell me before I continue. I did not rewrite or alter any history.

## 2. Risk register

Likelihood (L) / Impact (I): H, M, L.

| ID | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| R-1 | **Dataset-scope mismatch** FUELHH WIND vs WINDFOR (visible-to-ESO metered farms) → systematic bias (−1.8 GW observed) mis-attributed to forecast skill | H | H | Prominent scope banner + methodology text; never attribute cause; show bias separately from MAE/RMSE; keep as discussion item in demo; investigate `/evolution` & other datasets only if time and without changing core scope | analysis |
| R-2 | Hourly forecast vs half-hourly actual: step-hold assumption and unknown hour alignment (U-2) | H | M | Documented A-4; optional hourly-resolution toggle; alignment test showed ±1 % effect | analysis |
| R-3 | Cutoff ambiguity (D-1) and `publishTime` ≠ availability | H | M | Configurable cutoff + lag; presets; sensitivity visible; cutoff stated on every view | analysis |
| R-4 | Leakage: accidentally using forecasts published after cutoff or "latest" forecasts | M | H | Selection tests incl. adversarial cases; regression vs independent script; guard `publish < slot`; "why selected" UI exposes the rule | tests |
| R-5 | Misreading missing as zero | M | H | `Optional[float]` end-to-end; JSON `null`; chart gaps; tests for zero vs missing | tests |
| R-6 | **Local disk nearly full (≈0.9 GiB free)** — `node_modules`, Python venv, Docker images may not fit; failed installs corrupt state | H | H | Free ≥ 5 GB before M0; `uv` cache & npm cache pruning; avoid duplicate toolchains; test Docker build incrementally | user |
| R-7 | Elexon API change/outage/retention | L | M | Pinned snapshot; ingestion isolated; retries; documentation of query used | ingest |
| R-8 | Render free tier cold start (~1 min) disappoints reviewer | M | M | Frontend "service waking" UX; README note; keep-warm or Option B | deploy |
| R-9 | Over-claiming in Decision Intelligence (implying savings/purchase advice) | M | H | Fixed disclaimers; no £/volume; copy reviewed; tests assert absence | product |
| R-10 | Timezone/DST bugs | M | M | UTC internal; `zoneinfo`; DST fixtures; Jan has no DST so also tested synthetically | tests |
| R-11 | Time overrun | M | H | Vertical slice first; defined cut order (`03`); contingency 1 h | lead |
| R-12 | Identity leakage via git metadata, paths, README text | M | H | D-6 anonymous author; scan history before publishing; avoid absolute paths in docs/screenshots; check `package.json`/`pyproject` author fields | lead |
| R-13 | Licence/attribution non-compliance | L | M | Attribution in footer + README; confirm wording (U-8) | docs |
| R-14 | Small sample (31 days, autocorrelated) → overconfident buffers | H | M | Caveat text; in-sample labelling; effective-sample note; optional rolling-origin calibration | analysis |
| R-15 | Real-data anomalies (2026-01-15 missing/extra vintage, late actuals) mishandled | M | M | Real-excerpt fixtures; data-quality anomaly list | tests |
| R-16 | Docs vs data time convention mismatch (publication times appear 1 h earlier in UTC than documented list; seasonal change) | M | L | Never use nominal schedule; use observed `publishTime` | ingest |
| R-17 | Recharts performance/accessibility with 1,488 points | L | M | Display-only decimation; table view; keyboard nav tested | frontend |
| R-18 | Dependency supply-chain (typosquats) | L | M | Pinned exact versions via lockfiles; only well-known packages | lead |

## 3. Repository name recommendation
`fennel-ridge-q7k3` — random words + suffix, no relation to your name, employer or the assignment. Alternatives: `quartz-meadow-5x2d`, `lumen-oak-r8m4`. **Unverified** that these are free on GitHub (cannot check without an owner account/creating repos). Avoid words like "gridbricks", "wind-forecast" if you prefer the repo to be unlinked from the challenge.

## 4. Open data questions (from `04`)
U-1 asset coverage · U-2 hour alignment · U-3 documented schedule time zone · U-4 authoritative gate closure · U-5 rate limits/retention · U-6 FUELHH revisions · U-7 `/evolution` cross-check · U-8 licence wording.
Planned handling: U-7 can be closed in M1 (≈ 15 min) by comparing our vintage reconstruction with `/forecast/generation/wind/evolution` for a few slots; U-1/U-2/U-4 cannot be resolved from public docs and remain disclosed limitations.
