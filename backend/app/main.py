"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.logging import configure_logging

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="UK Wind Forecast Intelligence API",
        version="0.1.0",
        description=(
            "Retrospective evaluation of day-ahead wind forecasts (Elexon BMRS WINDFOR vs FUELHH)."
        ),
    )
    app.state.settings = settings

    @app.get(f"{API_PREFIX}/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
