"""Metric tests with hand-computed expectations. Inputs are SYNTHETIC."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from app.domain.metrics import (
    EMPTY_METRICS,
    ExtremeInterval,
    compute_metrics,
    coverage,
    coverage_level,
    elevated_days,
    error_histogram,
    error_quantiles,
    top_extremes,
)

ACTUAL = [100.0, 80.0, 0.0, 50.0]
FORECAST = [90.0, 100.0, 10.0, 50.0]  # errors: +10, -20, -10, 0   (methodology §4.1)


def test_golden_worked_example() -> None:
    m = compute_metrics(ACTUAL, FORECAST)
    assert m.n == 4
    assert m.mae == 10.0
    assert m.rmse == pytest.approx(math.sqrt(150))
    assert m.bias == -5.0
    assert m.p90_abs_error == pytest.approx(17.0)  # sorted |e| = 0,10,10,20 -> 10 + 0.7*10
    assert m.mean_actual == 57.5 and m.mean_forecast == 62.5
    assert m.nmae == pytest.approx(10.0 / 57.5)


def test_rmse_squared_equals_bias_squared_plus_std_squared() -> None:
    m = compute_metrics(ACTUAL, FORECAST)
    assert m.error_std == pytest.approx(math.sqrt(125))
    assert m.rmse**2 == pytest.approx(m.bias**2 + m.error_std**2)


def test_sign_convention_actual_above_forecast_is_positive() -> None:
    assert compute_metrics([150.0], [100.0]).bias == 50.0
    assert compute_metrics([100.0], [150.0]).bias == -50.0


def test_zero_actual_is_a_valid_value_not_missing() -> None:
    m = compute_metrics([0.0], [25.0])
    assert (
        m.n == 1 and m.bias == -25.0 and m.mae == 25.0 and m.nmae is None
    )  # mean actual 0 -> nMAE undefined


def test_no_matched_pairs_gives_none_not_zero_or_nan() -> None:
    m = compute_metrics([], [])
    assert m == EMPTY_METRICS and m.n == 0
    assert all(v is None for v in (m.mae, m.rmse, m.bias, m.p90_abs_error, m.error_std, m.nmae))


def test_single_pair_and_perfect_forecast() -> None:
    m = compute_metrics([7.0], [7.0])
    assert (m.mae, m.rmse, m.bias, m.p90_abs_error, m.error_std) == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_rejects_nonfinite_and_length_mismatch() -> None:
    with pytest.raises(ValueError):
        compute_metrics([1.0, float("nan")], [1.0, 2.0])
    with pytest.raises(ValueError):
        compute_metrics([1.0], [1.0, 2.0])


def test_large_values_do_not_overflow() -> None:
    m = compute_metrics([1e12, 2e12], [0.0, 0.0])
    assert m.mae == pytest.approx(1.5e12) and math.isfinite(m.rmse)  # type: ignore[arg-type]


def test_p90_matches_numpy_linear_on_random_data() -> None:
    rng = np.random.default_rng(1)
    a, f = rng.uniform(0, 20000, 500), rng.uniform(0, 20000, 500)
    m = compute_metrics(a.tolist(), f.tolist())
    assert m.p90_abs_error == pytest.approx(np.percentile(np.abs(a - f), 90, method="linear"))


# ------------------------------------------------------------------ coverage
def test_coverage_and_levels() -> None:
    assert coverage(1488, 1488) == 1.0 and coverage(744, 1488) == 0.5 and coverage(0, 48) == 0.0
    assert coverage(0, 0) is None  # undefined, not 0 or 1
    assert [coverage_level(c) for c in (1.0, 0.95, 0.949, 0.5, 0.49, None)] == [
        "ok", "ok", "partial", "partial", "low", "undefined",
    ]  # fmt: skip


# ------------------------------------------------------------------ distribution
def test_histogram_bins_are_anchored_half_open_and_sum_to_n() -> None:
    errs = [10.0, -20.0, -10.0, 0.0, -500.0, 500.0, 999.9, -500.1]
    bins = error_histogram(errs, 500.0)
    assert sum(b.count for b in bins) == len(errs)
    lookup = {(b.lower, b.upper): b.count for b in bins}
    assert lookup[(-500.0, 0.0)] == 3  # -20, -10, -500 (lower edge inclusive)
    assert lookup[(0.0, 500.0)] == 2  # 10, 0
    assert lookup[(500.0, 1000.0)] == 2  # 500, 999.9
    assert lookup[(-1000.0, -500.0)] == 1  # -500.1
    assert all(b.lower % 500 == 0 for b in bins)


def test_histogram_is_stable_for_subsets() -> None:
    full = {b.lower: b.count for b in error_histogram([-700.0, 10.0, 620.0], 500.0)}
    sub = {b.lower: b.count for b in error_histogram([10.0], 500.0)}
    assert full[0.0] == sub[0.0] == 1  # same anchoring regardless of the filter


def test_histogram_empty_and_bad_width() -> None:
    assert error_histogram([], 500.0) == []
    with pytest.raises(ValueError):
        error_histogram([1.0], 0)


def test_quantiles() -> None:
    assert error_quantiles([]) is None
    q = error_quantiles([float(i) for i in range(101)])
    assert q is not None and q[50] == 50.0 and q[5] == 5.0 and q[95] == 95.0


# ------------------------------------------------------------------ extremes
def iv(minutes: int, err: float) -> ExtremeInterval:
    return ExtremeInterval(
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes), err, 0.0, 0.0
    )


def test_extremes_sign_semantics_and_ties() -> None:
    items = [iv(0, 100), iv(30, -300), iv(60, 100), iv(90, -50), iv(120, 0), iv(150, 400)]
    under, over = top_extremes(items, 2)
    assert [x.error_mw for x in under] == [400, 100] and under[
        1
    ].start_utc.minute == 0  # tie -> earlier
    assert [x.error_mw for x in over] == [-300, -50]
    all_u, all_o = top_extremes(items, 10)
    assert len(all_u) == 4 - 1 and len(all_o) == 2  # zero error is in neither list


# ------------------------------------------------------------------ elevated days
def test_elevated_days_uses_percentile_and_coverage_filter() -> None:
    d = [date(2026, 1, i) for i in range(1, 6)]
    rmse = {d[0]: 10.0, d[1]: 20.0, d[2]: 30.0, d[3]: 40.0, d[4]: 500.0}
    cov = {k: 1.0 for k in d}
    assert elevated_days(rmse, cov) == [d[3], d[4]]  # >= P75 (40)
    cov[d[4]] = 0.5  # insufficient coverage -> ignored entirely
    assert elevated_days(rmse, cov) == [d[3]]  # P75 of 10,20,30,40 = 32.5 -> only 40
    assert elevated_days({}, {}) == []
