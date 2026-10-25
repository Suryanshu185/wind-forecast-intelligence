# syntax=docker/dockerfile:1.7
# Multi-stage build. Targets:
#   backend-dev  – Python + all dependencies (dev/test tools included); code is bind-mounted by compose
#   runtime      – (default) production image: FastAPI serving the API and the built React app

# ---------------------------------------------------------------------------------------------
FROM python:3.12-slim AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install uv==0.12.0
WORKDIR /app/backend

# ---------------------------------------------------------------------------------------------
FROM python-base AS backend-dev
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project
ENV PATH="/opt/venv/bin:${PATH}"
COPY backend/ ./
COPY data/ /app/data/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------------------------
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------------------------
FROM python-base AS runtime-deps
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    APP_ENV=production \
    DATA_SOURCE_MODE=snapshot \
    DATA_SNAPSHOT_DIR=/app/data/snapshots \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=runtime-deps /opt/venv /opt/venv
WORKDIR /app/backend
COPY backend/app ./app
COPY data/snapshots /app/data/snapshots
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
COPY NOTICE LICENSE /app/
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % os.environ.get('PORT','8000'),timeout=4)"
# Single worker: all data is held in-process (~25k rows); `$PORT` is injected by container hosts.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
