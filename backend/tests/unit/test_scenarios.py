"""Scenario tests with hand-computed expectations (SYNTHETIC inputs)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.analysis import Row
from app.domain.scenarios import (
    DISCLAIMER,
    by_forecast_level,
    by_hour_of_day,
    by_lead_time,
    error_bands,
    rolling_origin,
    underdelivery_buffers,
)


def mk(
    day: int, hour: int, actual: float, forecast: float, lead: float = 24.0, minute: int = 0
) -> Row:
    start = datetime(2026, 1, day, hour, minute, tzinfo=UTC)
    return Row(
        start_utc=start,
        end_utc=start + timedelta(minutes=30),
        delivery_date=date(2026, 1, day),
        actual_mw=actual,
        forecast_mw=forecast,
        error_mw=actual - forecast,
        status="MATCHED",
        forecast_published_at=start - timedelta(hours=lead),
        lead_time_h=lead,
        forecast_row_start=start.replace(minute=0),
        cutoff_utc=start - timedelta(hours=lead),
        vintages_total=3,
        vintages_eligible=2,
        vintages_after_cutoff=1,
        unavailable_reason=None,
        conflict_fallback=False,
        conflict_involved=False,
        actual_conflict=False,
    )


def test_buffers_hand_computed() -> None:
    errors = [-100.0, -50.0, 0.0, 50.0, 100.0]  # u = 100, 50, 0, -50, -100
    b = {x.confidence_pct: x for x in underdelivery_buffers(errors, (50, 80, 90))}
    assert b[50].buffer_mw == 0.0 and b[50].raw_quantile_mw == 0.0  # median u = 0
    assert b[80].raw_quantile_mw == pytest.approx(60.0)  # idx 3.2 on [-100,-50,0,50,100]
    assert b[90].buffer_mw == pytest.approx(80.0) and b[90].energy_mwh_per_sp == pytest.approx(40.0)


def test_buffers_are_monotonic_in_confidence_and_clipped_at_zero() -> None:
    errors = [float(x) for x in range(-300, 700, 7)]  # forecast mostly too LOW -> negative u
    bufs = underdelivery_buffers(errors)
    assert [x.buffer_mw for x in bufs] == sorted(x.buffer_mw for x in bufs)
    low = underdelivery_buffers([100.0, 200.0, 300.0], (50,))[0]
    assert low.raw_quantile_mw < 0 and low.buffer_mw == 0.0  # never negative


def test_buffers_bands_empty_input_and_bad_levels() -> None:
    assert underdelivery_buffers([]) == [] and error_bands([]) == []
    with pytest.raises(ValueError):
        underdelivery_buffers([1.0], (0,))
    with pytest.raises(ValueError):
        error_bands([1.0], (100,))


def test_error_band_is_central_interval() -> None:
    errors = [float(x) for x in range(-100, 101)]  # 201 evenly spaced points
    band = {b.confidence_pct: b for b in error_bands(errors, (80, 50))}
    assert band[80].lower_mw == pytest.approx(-80.0) and band[80].upper_mw == pytest.approx(80.0)
    assert band[50].lower_mw == pytest.approx(-50.0) and band[50].upper_mw == pytest.approx(50.0)


def test_breakdowns() -> None:
    rows = [
        mk(1, 10, 100, 90),
        mk(1, 10, 80, 100, minute=30),
        mk(1, 11, 50, 50),
        mk(2, 10, 70, 60, lead=40.0),
    ]
    hod = {b.label: b for b in by_hour_of_day(rows)}
    assert hod["10:00"].metrics.n == 3 and hod["11:00"].metrics.bias == 0.0
    assert hod["10:00"].metrics.bias == pytest.approx((10 - 20 + 10) / 3)
    lead = {b.label: b.metrics.n for b in by_lead_time(rows, 12)}
    assert lead == {"24-36 h": 3, "36-48 h": 1}
    lvl = by_forecast_level(rows, 2)
    assert sum(b.metrics.n for b in lvl) == 4 and len(lvl) == 2


def test_unmatched_rows_are_ignored_by_breakdowns() -> None:
    r = mk(1, 10, 100, 90)
    missing = Row(
        **{**{f: getattr(r, f) for f in r.__slots__}, "error_mw": None, "status": "ACTUAL_MISSING"}
    )  # type: ignore[arg-type]
    assert by_hour_of_day([missing]) == []


def test_rolling_origin_uses_only_days_up_to_d_minus_2() -> None:
    def month(d_minus_1_error: float, d_error: float) -> list[Row]:
        rows = [mk(day, 10, 100.0, 150.0) for day in range(1, 9)]  # days 1-8: u = +50 always
        rows += [mk(9, 10, 100.0, 100.0 - d_minus_1_error)]  # day 9 (= D-1)
        rows += [mk(10, 10, 100.0, 100.0 - d_error)]  # day 10 = D
        return rows

    a = rolling_origin(month(0.0, 0.0), 90, min_history_days=7)
    b = rolling_origin(month(-5000.0, -5000.0), 90, min_history_days=7)  # wild D-1 and D errors
    day10 = lambda res: next(x for x in res.days if x.delivery_date == date(2026, 1, 10))  # noqa: E731
    assert (
        day10(a).buffer_mw == day10(b).buffer_mw == pytest.approx(50.0)
    )  # no leakage from D-1 / D
    assert day10(a).history_days == 8  # days 1..8 only
    assert a.skipped_days >= 7


def test_rolling_origin_realised_coverage() -> None:
    rows = [mk(d, 10, 100.0, 150.0) for d in range(1, 9)]  # u=+50 on days 1-8
    rows += [
        mk(10, 10, 100.0, 140.0),
        mk(10, 11, 100.0, 160.0),
    ]  # day 10: u = 40 (within), 60 (exceeds 50)
    res = rolling_origin(rows, 95, min_history_days=7)
    d10 = next(x for x in res.days if x.delivery_date == date(2026, 1, 10))
    assert (d10.n, d10.within_buffer, d10.buffer_mw) == (2, 1, 50.0)
    assert res.realised_pct is not None and 0 <= res.realised_pct <= 100


def test_rolling_origin_with_no_eligible_days_reports_none() -> None:
    res = rolling_origin([mk(1, 10, 1.0, 2.0)], 90)
    assert res.days == [] and res.realised_pct is None and res.skipped_days == 1


def test_disclaimer_denies_recommendations() -> None:
    assert "not a purchase recommendation" in DISCLAIMER and "scenario" in DISCLAIMER.lower()
