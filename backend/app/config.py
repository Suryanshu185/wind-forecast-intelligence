"""Runtime configuration (environment-driven, validated)."""
from __future__ import annotations

from datetime import date, time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings loaded from environment variables / `.env` (see `.env.example`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    cors_allow_origins: str = ""  # comma separated; empty = same-origin only

    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    elexon_timeout_seconds: float = 60.0
    elexon_max_retries: int = Field(default=3, ge=0, le=10)

    data_source_mode: Literal["snapshot", "live", "synthetic"] = "snapshot"
    data_snapshot_dir: Path = REPO_ROOT / "data" / "snapshots"

    # Permitted delivery (settlement) date window - product scope is January 2026.
    analysis_start_date: date = date(2026, 1, 1)
    analysis_end_date: date = date(2026, 1, 31)

    # Defaults for analysis requests; all overridable per request.
    decision_timezone: str = "Europe/London"
    decision_cutoff_time: time = time(9, 50)
    decision_days_before_delivery: int = Field(default=1, ge=0, le=3)
    forecast_availability_lag_minutes: int = Field(default=0, ge=0, le=720)
    duplicate_conflict_policy: Literal["exclude", "strict"] = "exclude"
    hour_alignment: Literal["start", "end"] = "start"
    analysis_resolution: Literal["half_hour", "hourly"] = "half_hour"

    # Optional location of the built SPA (production image).
    frontend_dist_dir: Path | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
