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
