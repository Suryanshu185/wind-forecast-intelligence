"""Regression tests on the pinned REAL snapshot.

The golden numbers come from the INDEPENDENT stdlib probe (docs/planning/research/probe_elexon.py,
output in probe_output.txt) which was written before this code and shares none of it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.config import get_settings
from app.domain.analysis import AnalysisConfig, AnalysisResult, run_analysis
from app.repository.datasets import LoadedData, SnapshotRepository

JAN = (date(2026, 1, 1), date(2026, 1, 31))


@pytest.fixture(scope="module")
def data() -> LoadedData:
    return SnapshotRepository(get_settings().data_snapshot_dir).load()


def analyse(data: LoadedData, **kw) -> AnalysisResult:  # type: ignore[no-untyped-def]
    return run_analysis(data.actuals, data.forecasts, AnalysisConfig(*JAN, **kw))


# (cutoff, MAE, RMSE, bias) as printed by probe_output.txt (rounded to whole MW)
PROBE = [
    (time(9, 20), 2145, 2616, -1852),
    (time(9, 50), 2126, 2621, -1840),
    (time(12, 0), 2021, 2481, -1806),
    (time(15, 30), 1984, 2448, -1817),
    (time(23, 59), 1941, 2411, -1714),
]


@pytest.mark.parametrize(("cutoff", "mae", "rmse", "bias"), PROBE)
def test_reproduces_independent_probe_numbers(
    data: LoadedData, cutoff: time, mae: int, rmse: int, bias: int
) -> None:
    res = analyse(data, cutoff_time=cutoff)
    m = res.metrics
    assert res.counts.expected == 1488 and res.counts.matched == 1488 and res.counts.coverage == 1.0
    assert m.mae == pytest.approx(mae, abs=1.0)
    assert m.rmse == pytest.approx(rmse, abs=1.0)
    assert m.bias == pytest.approx(bias, abs=1.0)


def test_default_config_headline_numbers(data: LoadedData) -> None:
    res = analyse(data)
    assert res.config.cutoff_time == time(9, 50) and res.config.days_before == 1
    assert res.counts.balanced and res.counts_hourly.expected == 744
    assert res.metrics.rmse**2 == pytest.approx(res.metrics.bias**2 + res.metrics.error_std**2)  # type: ignore[operator]
    assert (
        res.over_forecast_count > res.under_forecast_count
    )  # forecast mostly above FUELHH actuals


def test_no_leakage_and_positive_lead_time_for_every_interval_and_cutoff(data: LoadedData) -> None:
    for cutoff in (time(9, 20), time(9, 50), time(15, 30)):
        for lag in (0, 45):
            res = analyse(data, cutoff_time=cutoff, availability_lag_minutes=lag)
            for r in res.sp_rows:
                assert r.forecast_published_at is not None
                assert r.forecast_published_at <= r.cutoff_utc
                assert r.forecast_published_at < r.start_utc.replace(minute=0)
                assert r.lead_time_h is not None and r.lead_time_h > 0


def test_every_selection_equals_a_brute_force_recomputation(data: LoadedData) -> None:
    for cutoff in (time(9, 20), time(9, 50)):
        res = analyse(data, cutoff_time=cutoff)
        by_stamp: dict[datetime, list] = {}
        for f in data.forecasts.records:
            by_stamp.setdefault(f.start_utc, []).append(f)
        for r in res.sp_rows[::7]:  # sample every 7th SP (212 checks) to keep the suite fast
            hour = r.start_utc.replace(minute=0)
            cutoff_utc = datetime.combine(r.delivery_date - timedelta(days=1), cutoff, tzinfo=UTC)
            best = max(
                (f for f in by_stamp[hour] if f.publish_utc <= cutoff_utc),
                key=lambda f: f.publish_utc,
            )
            assert (r.forecast_mw, r.forecast_published_at) == (best.mw, best.publish_utc)


def test_cutoff_0920_vs_0950_differ_exactly_by_the_0930_vintage(data: LoadedData) -> None:
    a, b = analyse(data, cutoff_time=time(9, 20)), analyse(data, cutoff_time=time(9, 50))
    pub_a = {
        r.forecast_published_at.strftime("%H:%M") for r in a.sp_rows if r.forecast_published_at
    }  # type: ignore[union-attr]
    pub_b = {
        r.forecast_published_at.strftime("%H:%M") for r in b.sp_rows if r.forecast_published_at
    }  # type: ignore[union-attr]
    assert "09:30" not in pub_a and "09:30" in pub_b
    assert a.metrics.mae != b.metrics.mae


def test_real_anomaly_2026_01_15_offschedule_vintage_is_used_when_eligible(
    data: LoadedData,
) -> None:
    """The 11:30Z vintage is absent on 2026-01-15 and a 12:25Z one exists. A nominal-schedule shortcut
    would be wrong; the algorithm must use what the data actually contains."""
    day = date(2026, 1, 16)
    cfg = dict(delivery_start=day, delivery_end=day, days_before=1)
    at_1230 = run_analysis(
        data.actuals, data.forecasts, AnalysisConfig(cutoff_time=time(12, 30), **cfg)
    )  # type: ignore[arg-type]
    at_1200 = run_analysis(
        data.actuals, data.forecasts, AnalysisConfig(cutoff_time=time(12, 0), **cfg)
    )  # type: ignore[arg-type]
    assert {r.forecast_published_at for r in at_1230.sp_rows} == {
        datetime(2026, 1, 15, 12, 25, tzinfo=UTC)
    }
    assert {r.forecast_published_at for r in at_1200.sp_rows} == {
        datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    }


def test_late_published_actuals_on_2026_01_15_are_still_matched(data: LoadedData) -> None:
    day = date(2026, 1, 15)
    res = run_analysis(data.actuals, data.forecasts, AnalysisConfig(day, day))
    late = [r for r in res.sp_rows if r.start_utc.hour in (10, 11)]
    assert len(late) == 4 and all(r.status == "MATCHED" for r in late)


def test_hour_alignment_end_is_a_sensitivity_only_and_runs(data: LoadedData) -> None:
    start, end = analyse(data), analyse(data, hour_alignment="end")
    assert end.counts.expected == 1488
    assert abs(end.metrics.bias - start.metrics.bias) < 50  # type: ignore[operator]  # ~5 MW observed in the probe
    assert end.metrics.mae != start.metrics.mae  # not identical, so the switch is a real option
