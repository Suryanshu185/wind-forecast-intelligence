"""Data access layer: turns a raw snapshot into normalised, provenance-tagged data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings
from app.domain.models import NormalisedActuals, NormalisedForecasts
from app.domain.normalise import normalise_actuals, normalise_forecasts
from app.ingestion.elexon_client import ElexonClient
from app.ingestion.snapshot import (
    RawSnapshot,
    build_manifest,
    encode_files,
    load_snapshot,
    raw_from_rows,
)
from app.ingestion.synthetic import build_synthetic_snapshot


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where the numbers came from. Attached to every analytic response."""

    mode: str  # snapshot | live | synthetic
    is_synthetic: bool
    retrieved_at: datetime
    data_sha256: str
    manifest: dict[str, Any]


@dataclass(slots=True)
class LoadedData:
    actuals: NormalisedActuals
    forecasts: NormalisedForecasts
    provenance: Provenance


class DatasetRepository(Protocol):
    def load(self) -> LoadedData: ...


def _from_raw(raw: RawSnapshot, mode: str) -> LoadedData:
    m = raw.manifest
    retrieved = datetime.strptime(m["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return LoadedData(
        actuals=normalise_actuals(raw.fuelhh_rows),
        forecasts=normalise_forecasts(raw.windfor_rows),
        provenance=Provenance(
            mode=mode,
            is_synthetic=bool(m["is_synthetic"]),
            retrieved_at=retrieved,
            data_sha256=m["data_sha256"],
            manifest=m,
        ),
    )


class SnapshotRepository:
    """Reads the pinned, hash-verified snapshot (default, offline, deterministic)."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def load(self) -> LoadedData:
        return _from_raw(load_snapshot(self._dir), "snapshot")


class SyntheticRepository:
    """Clearly-labelled synthetic data for development and tests only."""

    def __init__(self, seed: int = 20260101) -> None:
        self._seed = seed

    def load(self) -> LoadedData:
        return _from_raw(build_synthetic_snapshot(self._seed), "synthetic")


class LiveRepository:
    """Fetches from Elexon at load time (explicitly opt-in). Failures propagate - never silently
    replaced by other data."""

    def __init__(self, settings: Settings, delivery_start: date, delivery_end: date) -> None:
        self._s = settings
        self._start, self._end = delivery_start, delivery_end

    def load(self) -> LoadedData:
        publish_from = datetime(
            self._start.year, self._start.month, self._start.day, tzinfo=UTC
        ) - timedelta(days=5)
        publish_to = datetime(
            self._end.year, self._end.month, self._end.day, tzinfo=UTC
        ) + timedelta(days=4)
        with ElexonClient(
            self._s.elexon_base_url,
            timeout=self._s.elexon_timeout_seconds,
            max_retries=self._s.elexon_max_retries,
        ) as client:
            fh = client.fetch_fuelhh_wind(self._start, self._end)
            wf = client.fetch_windfor(publish_from, publish_to)
        fh_bytes, wf_bytes = encode_files(fh.rows, wf.rows)
        manifest = build_manifest(
            fuelhh_bytes=fh_bytes,
            windfor_bytes=wf_bytes,
            fuelhh_row_count=len(fh.rows),
            windfor_row_count=len(wf.rows),
            sources=[
                {
                    "dataset": r.request.dataset,
                    "endpoint": r.request.endpoint,
                    "query": r.request.query,
                    "url": r.request.url,
                    "rows_returned": r.request.row_count,
                }
                for r in (fh, wf)
            ],
            retrieved_at=max(fh.request.retrieved_at, wf.request.retrieved_at),
            delivery_start=self._start,
            delivery_end=self._end,
            publish_from=publish_from,
            publish_to=publish_to,
            is_synthetic=False,
            tool_version="live",
        )
        return _from_raw(raw_from_rows(fh.rows, wf.rows, manifest), "live")


def build_repository(settings: Settings) -> DatasetRepository:
    if settings.data_source_mode == "snapshot":
        return SnapshotRepository(settings.data_snapshot_dir)
    if settings.data_source_mode == "synthetic":
        return SyntheticRepository()
    return LiveRepository(settings, settings.analysis_start_date, settings.analysis_end_date)
