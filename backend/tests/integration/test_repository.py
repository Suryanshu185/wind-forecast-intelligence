"""Repository + synthetic-data tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.ingestion.snapshot import SnapshotNotFoundError
from app.ingestion.synthetic import SYNTHETIC_NOTICE, build_synthetic_snapshot
from app.repository.datasets import SnapshotRepository, SyntheticRepository, build_repository


def test_synthetic_snapshot_is_flagged_deterministic_and_realistically_shaped() -> None:
    a, b = build_synthetic_snapshot(), build_synthetic_snapshot()
    assert a.manifest["is_synthetic"] is True and a.manifest["notice"] == SYNTHETIC_NOTICE
    assert a.manifest["data_sha256"] == b.manifest["data_sha256"]
    assert len(a.fuelhh_rows) == 31 * 48
    vintages = {r["publishTime"] for r in a.windfor_rows}
    assert all(
        sum(1 for r in a.windfor_rows if r["publishTime"] == v) == 73 for v in list(vintages)[:5]
    )


def test_synthetic_repository_provenance_says_synthetic() -> None:
    data = SyntheticRepository().load()
    assert data.provenance.is_synthetic is True and data.provenance.mode == "synthetic"
    assert data.actuals.report.accepted_rows == 31 * 48
    assert data.forecasts.conflicts == [] and data.actuals.conflicts == []
    assert (
        data.provenance.retrieved_at.tzinfo is UTC
        or data.provenance.retrieved_at.utcoffset() is not None
    )


def test_build_repository_selects_by_mode(tmp_path: Path) -> None:
    assert isinstance(build_repository(Settings(data_source_mode="synthetic")), SyntheticRepository)
    repo = build_repository(Settings(data_source_mode="snapshot", data_snapshot_dir=tmp_path))
    assert isinstance(repo, SnapshotRepository)
    with pytest.raises(SnapshotNotFoundError):  # no silent fallback to other data
        repo.load()


def test_synthetic_data_never_contains_future_unrealistic_timestamps() -> None:
    snap = build_synthetic_snapshot()
    starts = sorted(r["startTime"] for r in snap.fuelhh_rows)
    assert starts[0] == "2026-01-01T00:00:00Z" and starts[-1] == "2026-01-31T23:30:00Z"
    assert datetime.strptime(snap.manifest["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ")
