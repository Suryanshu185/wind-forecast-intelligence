"""Vercel serverless entry point: exposes the FastAPI app (`app`) for all /api/* requests.

Vercel runs this file as a Python Function. The application code lives in ./backend/app, so that directory is put
on sys.path. The pinned January-2026 snapshot (./data/snapshots) is bundled with the function; the dataset is
loaded lazily on the first request (serverless hosts may not run ASGI lifespan events).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402,F401  (re-exported for Vercel)
