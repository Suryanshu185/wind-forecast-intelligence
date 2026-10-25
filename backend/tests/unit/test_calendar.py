"""Calendar & cutoff tests. Expected values verified against real FUELHH clock-change data
(2025-03-30: 46 SPs 00:00Z-22:30Z; 2025-10-26: 50 SPs 2025-10-25T23:00Z-2025-10-26T23:30Z)."""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.domain.calendar import (
    cutoff_instant,
    expected_sp_starts,
    expected_sp_starts_range,
    floor_hour,
    get_zone,
    local_midnight_utc,
    london_date,
)


def utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


# ------------------------------------------------------------------ expected interval counts
def test_normal_day_has_48_sps_and_january_has_1488() -> None:
    sps = expected_sp_starts(date(2026, 1, 1))
    assert len(sps) == 48 and sps[0] == utc(2026, 1, 1) and sps[-1] == utc(2026, 1, 1, 23, 30)
    assert len(expected_sp_starts_range(date(2026, 1, 1), date(2026, 1, 31))) == 1488


def test_spring_forward_day_has_46_sps() -> None:
    sps = expected_sp_starts(date(2025, 3, 30))
    assert len(sps) == 46 and sps[0] == utc(2025, 3, 30) and sps[-1] == utc(2025, 3, 30, 22, 30)


def test_autumn_back_day_has_50_sps() -> None:
    sps = expected_sp_starts(date(2025, 10, 26))
    assert len(sps) == 50
    assert sps[0] == utc(2025, 10, 25, 23) and sps[-1] == utc(2025, 10, 26, 23, 30)


def test_sps_are_contiguous_30_minute_utc_steps_across_a_dst_week() -> None:
    sps = expected_sp_starts_range(date(2025, 10, 24), date(2025, 10, 28))
    assert all(b - a == timedelta(minutes=30) for a, b in itertools.pairwise(sps))
    assert len(sps) == 48 * 4 + 50


def test_reversed_range_rejected() -> None:
    with pytest.raises(ValueError):
        expected_sp_starts_range(date(2026, 1, 2), date(2026, 1, 1))


# ------------------------------------------------------------------ date boundaries
def test_london_date_boundaries() -> None:
    assert london_date(utc(2026, 1, 1, 0, 0)) == date(2026, 1, 1)  # winter: London == UTC
    assert london_date(utc(2025, 12, 31, 23, 59)) == date(2025, 12, 31)
    assert london_date(utc(2025, 6, 30, 22, 59)) == date(2025, 6, 30)  # 23:59 BST
    assert london_date(utc(2025, 6, 30, 23, 0)) == date(2025, 7, 1)  # 00:00 BST next day


def test_local_midnight_utc_winter_and_summer() -> None:
    assert local_midnight_utc(date(2026, 1, 15)) == utc(2026, 1, 15)
    assert local_midnight_utc(date(2025, 7, 1)) == utc(2025, 6, 30, 23)


def test_naive_datetimes_rejected() -> None:
    with pytest.raises(ValueError):
        london_date(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        floor_hour(datetime(2026, 1, 1, 10, 30))


def test_floor_hour() -> None:
    assert floor_hour(utc(2026, 1, 1, 10, 59, 59)) == utc(2026, 1, 1, 10)


# ------------------------------------------------------------------ cutoff instants
def test_cutoff_is_previous_day_clock_time_winter() -> None:
    assert cutoff_instant(date(2026, 1, 10), time(9, 50)) == utc(2026, 1, 9, 9, 50)


def test_cutoff_in_summer_is_one_hour_earlier_in_utc() -> None:
    assert cutoff_instant(date(2025, 7, 10), time(9, 50)) == utc(2025, 7, 9, 8, 50)  # BST


def test_cutoff_crosses_year_and_month_boundaries() -> None:
    assert cutoff_instant(date(2026, 1, 1), time(9, 50)) == utc(2025, 12, 31, 9, 50)
    assert cutoff_instant(date(2026, 2, 1), time(15, 30)) == utc(2026, 1, 31, 15, 30)


@pytest.mark.parametrize(
    ("days_before", "expected"),
    [(0, utc(2026, 1, 10, 9, 50)), (1, utc(2026, 1, 9, 9, 50)), (2, utc(2026, 1, 8, 9, 50))],
)
def test_days_before_distinguishes_delivery_date_from_decision_date(
    days_before: int, expected: datetime
) -> None:
    assert cutoff_instant(date(2026, 1, 10), time(9, 50), days_before) == expected


def test_negative_days_before_rejected() -> None:
    with pytest.raises(ValueError):
        cutoff_instant(date(2026, 1, 10), time(9, 50), -1)


def test_cutoff_in_non_london_timezone() -> None:
    # 10:50 CET (UTC+1 in winter) == 09:50 GMT
    assert cutoff_instant(date(2026, 1, 10), time(10, 50), 1, get_zone("Europe/Paris")) == utc(
        2026, 1, 9, 9, 50
    )


def test_nonexistent_local_time_in_spring_gap_is_deterministic() -> None:
    # Decision date 2025-03-30: 01:30 London does not exist (01:00 GMT -> 02:00 BST).
    # Rule: pre-transition offset (GMT) applied -> 01:30Z, which is 02:30 BST.
    got = cutoff_instant(date(2025, 3, 31), time(1, 30))
    assert got == utc(2025, 3, 30, 1, 30)


def test_ambiguous_local_time_in_autumn_overlap_takes_first_occurrence() -> None:
    # Decision date 2025-10-26: 01:30 London occurs twice. First = BST (UTC+1) -> 00:30Z.
    got = cutoff_instant(date(2025, 10, 27), time(1, 30))
    assert got == utc(2025, 10, 26, 0, 30)


def test_unknown_timezone_rejected() -> None:
    with pytest.raises(ValueError):
        get_zone("Mars/Olympus_Mons")
