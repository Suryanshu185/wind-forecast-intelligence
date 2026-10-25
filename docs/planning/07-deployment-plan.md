# 07 — Deployment Plan

**Nothing has been deployed or published.** Deployment and repository publication require explicit approval.

## 1. Requirements that shape the choice
- Public URL, no login for visitors.
- FastAPI + pandas/NumPy backend, React SPA.
- Must be reliable for a reviewer who clicks the link cold, at an arbitrary time.
- Fit inside ~1.25 h of the budget; keep the Docker-based local workflow identical to production.

## 2. Platform compatibility findings (from official docs, fetched 2026-10-25)

| Platform | Finding | Source | Implication |
|---|---|---|---|
| **Render** (Docker web service, free) | Free web services supported for Python/Docker. **Spin down after 15 min idle; ~1 minute to spin back up** (a loading page is shown to browsers). Ephemeral filesystem. 750 free instance hours/month per workspace. Free instances are "not for production". Static sites are free. | render.com/docs/free | Docker image can be deployed as-is. Cold start ≈ 1 min is the main risk for a reviewer. Pinned snapshot in image avoids runtime ingestion, so cold start is bounded by container boot + pandas load. |
| **Vercel** (FastAPI on Python runtime) | FastAPI is supported through the Python runtime as Vercel Functions (entrypoint `app`/`main.py` or `tool.vercel.entrypoint`). **Bundle limit 500 MB for Python** (250 MB generally); function memory 2 GB (Hobby); max duration 300 s (Hobby). Frontend and backend in one project via **Vercel Services (marked beta)**, or serve static files from FastAPI (`public/`). Serverless: filesystem is read-only/ephemeral, no long-lived process. | vercel.com/docs/frameworks/backend/fastapi, /functions/limitations, /functions/runtimes/python | Technically compatible: pandas+numpy fit well under 500 MB and a pinned snapshot shipped in the bundle is readable. Needs non-Docker packaging (Vercel builds from source, not our Dockerfile) and verification of snapshot file inclusion (`includeFiles`) and import-time cost on cold start. Beta features should not be relied upon. Hobby-plan terms (non-commercial use) **[U]** not checked. |
| Fly.io / Railway / Cloud Run / AWS App Runner | Container hosts that would work with the same Dockerfile. **[U]** Not investigated in detail (free-tier terms change frequently; typically require a card). | — | Fallbacks only. |

## 3. Options

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A (recommended): single Docker image on Render** | Multi-stage image: build React → copy into Python image; FastAPI serves `/api/*` + SPA. Deploy as one Render Web Service from the public GitHub repo (Blueprint `render.yaml`). | Production ≡ `docker compose` image (the brief's Docker requirement is exercised in prod); one URL, no CORS; no platform-specific code; simple rollback; snapshot bundled. | Free-tier cold start (~1 min after 15 min idle). Mitigation: README + in-app "waking up" message (frontend retry with friendly loading state), optional keep-warm ping (note: not part of app code), or paid starter instance if budget allows. |
| B: Vercel static frontend + Vercel FastAPI function | Two parts under one Vercel project or two projects. | No cold-start "minute"; fast CDN for SPA; free. | Different runtime than local Docker (needs `vercel.json`, entrypoint conventions, snapshot inclusion); Services beta; 2 deployment mechanisms to document; more risk of last-hour surprises. |
| C: Vercel frontend + Render backend | Split hosting. | SPA always fast. | CORS + two URLs + backend still cold-starts. Worst of both for little gain. |

**Recommendation: Option A.** It minimises divergence between what the reviewer runs locally (`docker compose up`) and what is deployed, and avoids relying on beta platform features. Option B is the documented fallback if cold start proves unacceptable in the spike (it is the better UX at the cost of more platform-specific plumbing).
Final choice → decision D-4.

## 4. Deployment steps (Option A) — to be executed only after approval
1. (Approval required) Create the GitHub repo with the anonymous name; push `main`.
2. Add `render.yaml` (service type `web`, `runtime: docker`, plan `free`, health check `/api/v1/health`, env vars from `.env.example`, `PORT` provided by Render).
3. Connect repo in Render; deploy; wait for healthy.
4. Smoke test: `/api/v1/health`, `/api/v1/meta`, load SPA, run default analysis, confirm provenance badge says real snapshot and counts equal 1,488.
5. Record the URL in README; re-verify unauthenticated access from a private browser window.
6. Performance sanity: cold start timing documented in README.

Early spike (during M0/M1, after approval): deploy a throwaway hello-world container to confirm the pipeline and measure cold start (≈ 15 min).

## 5. Production configuration
- `APP_ENV=production`, `DATA_SOURCE_MODE=snapshot` (never `live` in prod), `LOG_LEVEL=INFO`, `CORS_ALLOW_ORIGINS` empty (same origin).
- Container runs as non-root, `uvicorn --workers 1` (memory-light, data is in-process, 1 worker is enough), `--proxy-headers`.
- Security headers via middleware (CSP allowing self + inline styles required by Recharts), `X-Content-Type-Options`, `Referrer-Policy`.
- No secrets required. No database. No outbound network calls at runtime.

## 6. Pre-publication checklist (brief §10)
Repository name anonymous · commit author/committer identities anonymous (see D-6) · no secrets/personal data (`git log -p | grep` scan + `gitleaks`-style review) · no unintended datasets (only reviewed snapshot) · README complete · Docker workflow verified from a clean clone · tests green · final commit is the reviewed submission · public access verified in a logged-out browser · deployment URL in README · attribution & AI-usage disclosure present.


---

## 7. Decision update (2026-10-25): Vercel is the deployment target

The owner chose Vercel. Consequences relative to the options above (this is "Option B" in §3, now implemented):
- Static UI from the Vercel CDN (no cold start for the UI); `/api/*` served by one Python Function (`api/index.py`) that imports the existing FastAPI app. The snapshot is bundled via `functions.includeFiles`; dependencies come from the lockfile-derived `requirements.txt` (≈ 80 MB installed, well under the 500 MB limit).
- Serverless hosts may not run ASGI lifespan events, so the dataset is now loaded lazily on first request (a failed load is reported as 503 and retried; no substitute data).
- The function has a cold start (Python + pandas import, then a ≈ 25k-row snapshot load); not yet measured. The UI's error state already explains a slow first request.
- `render.yaml` was removed. The Dockerfile/compose files remain for local use and other container hosts.
- Still unverified until a real deployment: build success, rewrite behaviour (`/api/*` → function, SPA fallback), response headers, cold-start time, Vercel plan limits for the chosen account type (including Hobby plan terms on non-commercial use).


---

## 8. First Vercel deployment failed — diagnosis and fix (2026-10-26)

**Symptom.** The first production deployment built "successfully" and reported Ready, but every route returned
`500 FUNCTION_INVOCATION_FAILED` with no runtime log entries. The build log warned "FastAPI static file collection failed".

**Confirmed facts** (each checked against the build output, Vercel's API, or the builder's own source):
1. Vercel detected `framework: fastapi` and used `@vercel/python` 28.0.1. The function bundle was ~2.5 MB; its vendored
   packages were only `pip` and `vercel_runtime` — **no FastAPI, Starlette, Pydantic, pandas, NumPy or httpx**. The app code
   and the snapshot *were* included.
2. The project's stored `installCommand` (`cd frontend && npm ci ...`, saved from our `vercel.json` by the first deploy) was
   in effect. In the builder source, a non-empty `installCommand` is the *only* install step run: it sets
   `assumeDepsInstalled = true` and skips the builder's own `uv`/`requirements.txt` installation. Removing the setting
   restored the log line `Installing required dependencies from requirements.txt`.
3. The "static file collection failed" warning is a downstream symptom: the builder imports the app from the (empty) venv to
   discover static mounts, which cannot succeed without FastAPI installed.
4. The stored project `buildCommand` ran inside the Python build step, but its output (`frontend/dist`) was published nowhere
   (the deployment contained no static files), so the UI was missing as well.
5. Settings in `vercel.json` do **not** clear values already stored on the project (stripping the file left the old
   overrides active); the stored project settings had to be corrected too.
6. The uploaded source contained no `.env*` or `.vercel` state (checked via the deployment files API).

**Hypotheses not adopted.** Moving the frontend build into Python (pyproject build script) was not needed; `app.frontend()`
CDN promotion was not used because the builder suppresses CDN mounts when the app has middleware (ours has several).

**Fix (smallest change supported by the evidence).** One Vercel project, FastAPI preset:
- no `installCommand` (the builder installs `requirements.txt`);
- `buildCommand`: `cd frontend && npm ci && npm run build` (runs after the Python install, before bundling);
- the function bundles `frontend/dist`, `backend/app` and `data/snapshots`, and serves the UI itself through the existing,
  tested SPA route (CSP and security headers are set by the app, so `vercel.json` carries no `headers`/`rewrites`);
- `api/index.py` points `FRONTEND_DIST_DIR` at the bundled build;
- stored project settings were corrected to match.

**Verification of the fix before deploying.** `vercel build` output inspected: all 12 required packages vendored as Linux
x86_64 wheels, snapshot + 26 app modules + UI bundled, ~114 MB of the 500 MB limit, no credentials or `node_modules`.
The bundle cannot be executed on a macOS arm64 machine (Linux binaries), so runtime verification is done on a Vercel preview.
