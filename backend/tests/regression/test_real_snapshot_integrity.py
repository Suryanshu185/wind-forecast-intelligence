"""Checks on the pinned REAL Elexon snapshot (data/snapshots). Expected values come from the
independent research probe (docs/planning/research/probe_output.txt), not from this code."""

from __future__ import annotations

from collections import Counter

import pytest

from app.config import get_settings
from app.repository.datasets import LoadedData, SnapshotRepository


@pytest.fixture(scope="module")
def data() -> LoadedData:
    return SnapshotRepository(get_settings().data_snapshot_dir).load()


def test_provenance_is_real_and_complete(data: LoadedData) -> None:
    p = data.provenance
    assert p.mode == "snapshot" and p.is_synthetic is False
    m = p.manifest
    assert m["retrieved_at"].endswith("Z") and m["attribution"] and m["limitations"]
    assert m["period_covered"]["delivery_start"] == "2026-01-01"
    assert m["period_covered"]["delivery_end"] == "2026-01-31"
    assert {s["dataset"] for s in m["sources"]} == {"FUELHH", "WINDFOR"}
    assert all("data.elexon.co.uk" in s["url"] for s in m["sources"])


def test_actuals_match_probe_findings(data: LoadedData) -> None:
    rep = data.actuals.report
    assert rep.accepted_rows == 1488 and rep.input_rows == 1488
    assert (rep.rejected_rows, rep.conflicting_keys, rep.duplicate_rows_collapsed) == (0, 0, 0)
    assert (rep.null_generation_rows, rep.zero_generation_rows, rep.off_grid_rows) == (0, 0, 0)
    assert rep.settlement_date_mismatches == 0
    per_day = Counter(r.settlement_date for r in data.actuals.records)
    assert len(per_day) == 31 and set(per_day.values()) == {48}
    mws = [r.mw for r in data.actuals.records if r.mw is not None]
    assert (min(mws), max(mws)) == (1695.0, 17805.0)


def test_forecasts_match_probe_findings(data: LoadedData) -> None:
    rep = data.forecasts.report
    assert rep.accepted_rows == 22776 and rep.input_rows == 22776
    assert (
        rep.rejected_rows,
        rep.conflicting_keys,
        rep.duplicate_rows_collapsed,
        rep.off_grid_rows,
    ) == (0, 0, 0, 0)
    vintages = Counter(r.publish_utc for r in data.forecasts.records)
    assert len(vintages) == 312 and set(vintages.values()) == {73}
    assert all(r.start_utc.minute == 0 for r in data.forecasts.records)


def test_documented_anomalies_present_in_real_data(data: LoadedData) -> None:
    pubs = {r.publish_utc.strftime("%Y-%m-%dT%H:%M") for r in data.forecasts.records}
    assert "2026-01-15T12:25" in pubs  # off-schedule vintage
    assert "2026-01-15T11:30" not in pubs  # expected vintage absent
    late = [
        r for r in data.actuals.records if (r.publish_utc - r.start_utc).total_seconds() / 60 > 30
    ]
    assert sorted(r.settlement_period for r in late) == [21, 22, 23, 24]
