"""Vercel serverless entry point: exposes the FastAPI app (`app`) for all /api/* requests.

Vercel runs this file as a Python Function (FastAPI preset: every request is routed here). The application code lives in ./backend/app, so that directory is put
on sys.path. The pinned January-2026 snapshot (./data/snapshots) is bundled with the function; the dataset is
loaded lazily on the first request (serverless hosts may not run ASGI lifespan events).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
# The React build (frontend/dist) is produced by the project build command and bundled with this function.
os.environ.setdefault("FRONTEND_DIST_DIR", str(ROOT / "frontend" / "dist"))

from app.main import app  # noqa: E402,F401  (re-exported for Vercel)
