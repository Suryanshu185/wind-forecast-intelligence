"""End-to-end analysis tests on a tiny hand-built SYNTHETIC scenario with exactly known answers.

Scenario (all UTC; January => London == UTC). Delivery date 2026-01-02, hours 10:00 and 11:00 only carry data.
Forecast vintages for hour 10:00 (hourly WINDFOR rows):
    2026-01-01 07:30Z -> 1000      2026-01-01 09:30Z -> 1100      2026-01-02 02:30Z -> 5000 (after any D-1 cutoff)
Forecast vintages for hour 11:00:
    2026-01-01 07:30Z -> 2000      2026-01-01 09:30Z -> 2200
Actuals: SP 10:00 = 1200, 10:30 = 1000, 11:00 = 2000, 11:30 = 2400.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time

import pytest

from app.domain.analysis import AnalysisConfig, run_analysis
from app.domain.models import (
    ActualRecord,
    Conflict,
    ForecastRecord,
    NormalisationReport,
    NormalisedActuals,
    NormalisedForecasts,
)

D = date(2026, 1, 2)


def utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


def fc(hour: int, pub: datetime, mw: float | None) -> ForecastRecord:
    return ForecastRecord(utc(2026, 1, 2, hour), pub, mw)


def act(h: int, m: int, mw: float | None) -> ActualRecord:
    t = utc(2026, 1, 2, h, m)
    return ActualRecord(t, t, mw, D, h * 2 + m // 30 + 1)


P0730, P0930, PDAY = utc(2026, 1, 1, 7, 30), utc(2026, 1, 1, 9, 30), utc(2026, 1, 2, 2, 30)


def forecasts(extra: list[ForecastRecord] | None = None, conflicts: list[Conflict] | None = None):
    recs = [
        fc(10, P0730, 1000),
        fc(10, P0930, 1100),
        fc(10, PDAY, 5000),
        fc(11, P0730, 2000),
        fc(11, P0930, 2200),
        *(extra or []),
    ]
    return NormalisedForecasts(recs, conflicts or [], NormalisationReport("WINDFOR"))


def actuals(recs: list[ActualRecord] | None = None, conflicts: list[Conflict] | None = None):
    base = [act(10, 0, 1200), act(10, 30, 1000), act(11, 0, 2000), act(11, 30, 2400)]
    return NormalisedActuals(
        base if recs is None else recs, conflicts or [], NormalisationReport("FUELHH")
    )


def cfg(**kw) -> AnalysisConfig:  # type: ignore[no-untyped-def]
    return AnalysisConfig(delivery_start=D, delivery_end=D, **kw)


def only_matched(res):  # type: ignore[no-untyped-def]
    return {
        r.start_utc.hour * 60 + r.start_utc.minute: r for r in res.rows if r.status == "MATCHED"
    }


# ------------------------------------------------------------------ the core point-in-time rule
def test_cutoff_0950_selects_0930_vintage_and_metrics_match_hand_calculation() -> None:
    res = run_analysis(actuals(), forecasts(), cfg(cutoff_time=time(9, 50)))
    m = only_matched(res)
    # forecasts: hour10 -> 1100, hour11 -> 2200 ; errors: 100, -100, -200, 200
    assert {k: r.error_mw for k, r in m.items()} == {600: 100, 630: -100, 660: -200, 690: 200}
    assert all(r.forecast_published_at == P0930 for r in m.values())
    assert res.metrics.n == 4
    assert res.metrics.mae == 150.0 and res.metrics.bias == 0.0
    assert res.metrics.rmse == pytest.approx(math.sqrt((100**2 * 2 + 200**2 * 2) / 4))
    assert res.metrics.p90_abs_error == pytest.approx(
        200.0
    )  # sorted |e| = 100,100,200,200; idx 2.7 -> 200


def test_cutoff_0920_selects_earlier_vintage_and_changes_the_numbers() -> None:
    res = run_analysis(actuals(), forecasts(), cfg(cutoff_time=time(9, 20)))
    m = only_matched(res)
    # forecasts: hour10 -> 1000, hour11 -> 2000 ; errors: 200, 0, 0, 400
    assert {k: r.error_mw for k, r in m.items()} == {600: 200, 630: 0, 660: 0, 690: 400}
    assert all(r.forecast_published_at == P0730 for r in m.values())
    assert res.metrics.mae == 150.0 and res.metrics.bias == 150.0
    assert res.exact_count == 2 and res.under_forecast_count == 2 and res.over_forecast_count == 0


def test_forecast_published_after_cutoff_never_leaks_into_results() -> None:
    res = run_analysis(actuals(), forecasts(), cfg())
    assert 5000.0 not in {r.forecast_mw for r in res.rows}
    assert all(
        r.forecast_published_at is None or r.forecast_published_at <= r.cutoff_utc for r in res.rows
    )


def test_availability_lag_changes_selection() -> None:
    res = run_analysis(
        actuals(), forecasts(), cfg(cutoff_time=time(9, 50), availability_lag_minutes=21)
    )
    assert {r.forecast_published_at for r in res.rows if r.forecast_mw is not None} == {P0730}


def test_decision_date_differs_from_delivery_date() -> None:
    res = run_analysis(actuals(), forecasts(), cfg())
    r = res.rows[20]  # 10:00 SP
    assert r.delivery_date == D and r.cutoff_utc == utc(2026, 1, 1, 9, 50)


def test_hourly_forecast_is_shared_by_both_half_hours() -> None:
    res = run_analysis(actuals(), forecasts(), cfg())
    by = {(r.start_utc.hour, r.start_utc.minute): r for r in res.rows}
    assert by[(10, 0)].forecast_mw == by[(10, 30)].forecast_mw == 1100.0
    assert by[(10, 0)].forecast_row_start == by[(10, 30)].forecast_row_start == utc(2026, 1, 2, 10)


# ------------------------------------------------------------------ expected/missing accounting
def test_counts_are_calendar_based_and_balance() -> None:
    res = run_analysis(actuals(), forecasts(), cfg())
    c = res.counts
    assert c.expected == 48  # from the calendar, not from the data rows
    assert c.matched == 4 and c.actual_observed == 4 and c.forecast_available == 4
    assert c.forecast_unavailable == 0 and c.actual_missing == 0 and c.both_missing == 44
    assert c.balanced and c.coverage == pytest.approx(4 / 48)
    assert res.coverage_level == "low"


def test_missing_actual_is_not_zero_and_excluded_from_metrics() -> None:
    acts = [act(10, 0, 1200), act(10, 30, None), act(11, 0, 2000), act(11, 30, 2400)]
    res = run_analysis(actuals(acts), forecasts(), cfg())
    row = next(r for r in res.rows if r.start_utc == utc(2026, 1, 2, 10, 30))
    assert row.status == "ACTUAL_MISSING" and row.actual_mw is None and row.error_mw is None
    assert res.counts.matched == 3 and res.counts.actual_missing == 1
    assert res.metrics.n == 3


def test_zero_actual_is_matched_as_a_real_value() -> None:
    acts = [act(10, 0, 0), act(10, 30, 1000), act(11, 0, 2000), act(11, 30, 2400)]
    res = run_analysis(actuals(acts), forecasts(), cfg())
    row = next(r for r in res.rows if r.start_utc == utc(2026, 1, 2, 10))
    assert row.status == "MATCHED" and row.actual_mw == 0.0 and row.error_mw == -1100.0


def test_unavailable_forecast_is_reported_not_zero_filled() -> None:
    res = run_analysis(actuals(), forecasts(), cfg(cutoff_time=time(3, 0)))  # before any vintage
    assert res.counts.matched == 0 and res.counts.forecast_unavailable == 4
    assert res.metrics.n == 0 and res.metrics.mae is None and res.metrics.rmse is None
    row = next(r for r in res.rows if r.start_utc == utc(2026, 1, 2, 10))
    assert row.status == "FORECAST_UNAVAILABLE" and row.forecast_mw is None
    assert row.unavailable_reason == "no_eligible_forecast" and row.vintages_after_cutoff == 3
    assert res.counts.coverage == 0.0


def test_actual_present_in_data_for_other_dates_is_ignored() -> None:
    other = ActualRecord(utc(2026, 1, 3, 10), utc(2026, 1, 3, 10), 9.0, date(2026, 1, 3), 21)
    res = run_analysis(actuals([*actuals().records, other]), forecasts(), cfg())
    assert res.counts.expected == 48 and res.unexpected_actual_rows == 0


def test_matching_is_by_delivery_interval_not_publish_time() -> None:
    # Make the ACTUAL for 10:00 carry a late publish time; it must still pair with the 10:00 forecast.
    late = ActualRecord(utc(2026, 1, 2, 10), utc(2026, 1, 2, 23), 1200.0, D, 21)
    acts = [late, act(10, 30, 1000), act(11, 0, 2000), act(11, 30, 2400)]
    res = run_analysis(actuals(acts), forecasts(), cfg())
    assert only_matched(res)[600].error_mw == 100


# ------------------------------------------------------------------ conflicts
def test_conflicted_actual_becomes_missing_and_is_flagged() -> None:
    acts = [act(10, 30, 1000), act(11, 0, 2000), act(11, 30, 2400)]
    conflicts = [Conflict("FUELHH", utc(2026, 1, 2, 10), None, (1200.0, 1300.0), 2)]
    res = run_analysis(actuals(acts, conflicts), forecasts(), cfg())
    row = next(r for r in res.rows if r.start_utc == utc(2026, 1, 2, 10))
    assert row.status == "ACTUAL_MISSING" and row.actual_conflict
    assert res.counts.conflict_affected >= 1


def test_conflicted_latest_forecast_exclude_vs_strict() -> None:
    recs = [
        fc(10, P0730, 1000),
        fc(11, P0730, 2000),
        fc(11, P0930, 2200),
    ]  # 10:00 @09:30 removed (conflicted)
    conflicts = [Conflict("WINDFOR", utc(2026, 1, 2, 10), P0930, (1100.0, 1111.0), 2)]
    fx = NormalisedForecasts(recs, conflicts, NormalisationReport("WINDFOR"))
    ex = run_analysis(actuals(), fx, cfg(conflict_policy="exclude"))
    st = run_analysis(actuals(), fx, cfg(conflict_policy="strict"))
    r_ex = next(r for r in ex.rows if r.start_utc == utc(2026, 1, 2, 10))
    r_st = next(r for r in st.rows if r.start_utc == utc(2026, 1, 2, 10))
    assert r_ex.forecast_mw == 1000.0 and r_ex.conflict_fallback  # older clean vintage, flagged
    assert r_st.forecast_mw is None and r_st.unavailable_reason == "conflict"
    assert ex.counts.conflict_affected == 2 and st.counts.forecast_unavailable == 2


# ------------------------------------------------------------------ alignment sensitivity
def test_end_alignment_uses_the_next_stamped_row_for_the_same_hour() -> None:
    # Under "end", the hour [10:00, 11:00) is described by the row stamped 11:00.
    res = run_analysis(actuals(), forecasts(), cfg(hour_alignment="end"))
    by = {(r.start_utc.hour, r.start_utc.minute): r for r in res.rows}
    assert by[(10, 0)].forecast_row_start == utc(2026, 1, 2, 11)
    assert by[(10, 0)].forecast_mw == 2200.0  # the 11:00 row's latest eligible vintage
    assert by[(11, 0)].forecast_mw is None  # row stamped 12:00 does not exist in this fixture


# ------------------------------------------------------------------ hourly view
def test_native_hourly_view_uses_mean_of_both_half_hours() -> None:
    res = run_analysis(actuals(), forecasts(), cfg(resolution="hourly"))
    assert res.counts.expected == 24 and res.counts.matched == 2
    rows = {r.start_utc.hour: r for r in res.rows if r.status == "MATCHED"}
    assert (
        rows[10].actual_mw == 1100.0 and rows[10].forecast_mw == 1100.0 and rows[10].error_mw == 0.0
    )
    assert rows[11].actual_mw == 2200.0 and rows[11].error_mw == 0.0
    assert res.metrics.n == 2 and res.metrics.mae == 0.0
    assert res.counts_half_hour.expected == 48 and res.counts_hourly.expected == 24


def test_hourly_view_does_not_fill_a_missing_half_hour() -> None:
    acts = [act(10, 0, 1200), act(10, 30, None), act(11, 0, 2000), act(11, 30, 2400)]
    res = run_analysis(actuals(acts), forecasts(), cfg(resolution="hourly"))
    h10 = next(r for r in res.rows if r.start_utc.hour == 10)
    assert h10.status == "ACTUAL_MISSING" and h10.actual_mw is None
    assert res.counts.matched == 1


# ------------------------------------------------------------------ daily / dst
def test_daily_results_carry_their_own_denominators() -> None:
    res = run_analysis(actuals(), forecasts(), cfg())
    assert len(res.daily) == 1
    d = res.daily[0]
    assert d.delivery_date == D and d.counts.expected == 48 and d.counts.matched == 4
    assert d.metrics.mae == 150.0


def test_dst_days_have_46_and_50_expected_sps() -> None:
    for day, n, hours in ((date(2025, 3, 30), 46, 23), (date(2025, 10, 26), 50, 25)):
        res = run_analysis(
            actuals([]), forecasts(), AnalysisConfig(delivery_start=day, delivery_end=day)
        )
        assert res.counts.expected == n and res.counts_hourly.expected == hours
