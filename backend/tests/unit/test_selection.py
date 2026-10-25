"""Forecast-vintage selection tests (the critical algorithm). All data SYNTHETIC, hand-built."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models import Conflict, ForecastRecord
from app.domain.selection import ForecastIndex


def utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


TARGET = utc(2026, 1, 2, 10)  # delivery hour 10:00-11:00Z on 2 Jan
P_0430, P_0730, P_0930, P_1130 = (
    utc(2026, 1, 1, h, m) for h, m in [(4, 30), (7, 30), (9, 30), (11, 30)]
)
P_NEXT_DAY = utc(2026, 1, 2, 2, 30)


def vintages() -> list[ForecastRecord]:
    return [
        ForecastRecord(TARGET, P_0430, 100.0),
        ForecastRecord(TARGET, P_0730, 110.0),
        ForecastRecord(TARGET, P_0930, 120.0),
        ForecastRecord(TARGET, P_1130, 130.0),
        ForecastRecord(TARGET, P_NEXT_DAY, 140.0),  # published on delivery day
    ]


def select(cutoff, recs=None, conflicts=None, policy="exclude"):  # type: ignore[no-untyped-def]
    idx = ForecastIndex(recs if recs is not None else vintages(), conflicts)
    return idx.select(TARGET, TARGET, cutoff, policy)


def without(publish: datetime) -> list[ForecastRecord]:
    return [r for r in vintages() if r.publish_utc != publish]


# ------------------------------------------------------------------ latest eligible & exclusion
def test_selects_latest_vintage_published_at_or_before_cutoff() -> None:
    s = select(utc(2026, 1, 1, 9, 50))
    assert s.forecast_mw == 120.0 and s.published_at == P_0930
    assert s.available and s.reason is None
    assert s.lead_time_h == pytest.approx(24.5)  # 09:30 D-1 -> 10:00 D
    assert (s.vintages_total, s.vintages_eligible, s.vintages_after_cutoff) == (5, 3, 2)


def test_forecast_published_after_cutoff_is_excluded_even_if_newer() -> None:
    s = select(utc(2026, 1, 1, 9, 20))
    assert s.forecast_mw == 110.0 and s.published_at == P_0730  # 09:30 vintage is 10 min too late


def test_vintage_published_exactly_at_cutoff_is_eligible() -> None:
    assert select(P_0930).forecast_mw == 120.0
    assert select(P_0930 - timedelta(seconds=1)).forecast_mw == 110.0


def test_latest_overall_forecast_is_not_used_for_a_historical_decision() -> None:
    latest_overall = max(vintages(), key=lambda r: r.publish_utc)
    s = select(utc(2026, 1, 1, 9, 50))
    assert latest_overall.mw == 140.0 and s.forecast_mw != latest_overall.mw


def test_availability_lag_moves_effective_cutoff_earlier() -> None:
    cutoff = utc(2026, 1, 1, 9, 50)
    assert select(cutoff - timedelta(minutes=20)).forecast_mw == 120.0  # lag 20 -> effective 09:30
    assert select(cutoff - timedelta(minutes=21)).forecast_mw == 110.0  # lag 21 -> effective 09:29


def test_effective_cutoff_is_reported() -> None:
    cutoff = utc(2026, 1, 1, 9, 30)
    assert select(cutoff).cutoff_utc == cutoff


# ------------------------------------------------------------------ unavailable
def test_no_eligible_forecast_is_unavailable_not_zero() -> None:
    s = select(utc(2026, 1, 1, 3, 0))
    assert s.forecast_mw is None and s.published_at is None and s.lead_time_h is None
    assert s.reason == "no_eligible_forecast" and not s.available
    assert s.vintages_total == 5 and s.vintages_eligible == 0 and s.vintages_after_cutoff == 5


def test_no_vintages_at_all_is_unavailable() -> None:
    s = select(utc(2026, 1, 1, 9, 50), recs=[])
    assert s.forecast_mw is None and s.reason == "no_eligible_forecast" and s.vintages_total == 0


def test_zero_mw_forecast_is_a_valid_selection_not_missing() -> None:
    s = select(utc(2026, 1, 1, 9, 50), [ForecastRecord(TARGET, P_0730, 0.0)])
    assert s.forecast_mw == 0.0 and s.available


def test_null_value_in_latest_vintage_falls_back_to_earlier_vintage() -> None:
    recs = [ForecastRecord(TARGET, P_0730, 110.0), ForecastRecord(TARGET, P_0930, None)]
    s = select(utc(2026, 1, 1, 9, 50), recs)
    assert s.forecast_mw == 110.0 and s.published_at == P_0730


def test_only_null_vintages_is_unavailable() -> None:
    s = select(utc(2026, 1, 1, 9, 50), [ForecastRecord(TARGET, P_0730, None)])
    assert s.forecast_mw is None and s.reason == "no_eligible_forecast"


def test_backcast_rows_published_after_the_hour_started_are_never_eligible() -> None:
    recs = [
        ForecastRecord(TARGET, P_0730, 110.0),
        ForecastRecord(TARGET, utc(2026, 1, 2, 12, 30), 999.0),
    ]
    assert (
        select(utc(2026, 1, 3), recs).forecast_mw == 110.0
    )  # cutoff after delivery (days_before<0 abuse)


def test_vintage_published_exactly_at_hour_start_is_not_eligible() -> None:
    recs = [ForecastRecord(TARGET, P_0730, 110.0), ForecastRecord(TARGET, TARGET, 777.0)]
    assert select(utc(2026, 1, 3), recs).forecast_mw == 110.0


def test_other_target_hours_are_never_consulted() -> None:
    recs = [ForecastRecord(TARGET + timedelta(hours=1), P_0930, 555.0)]
    assert select(utc(2026, 1, 1, 9, 50), recs).forecast_mw is None


# ------------------------------------------------------------------ determinism
def test_selection_independent_of_input_order() -> None:
    recs = vintages()
    base = select(utc(2026, 1, 1, 9, 50), recs)
    for seed in range(20):
        shuffled = recs[:]
        random.Random(seed).shuffle(shuffled)
        assert select(utc(2026, 1, 1, 9, 50), shuffled) == base


# ------------------------------------------------------------------ conflicts
def conflict(publish: datetime) -> Conflict:
    return Conflict("WINDFOR", TARGET, publish, (500.0, 900.0), 2)


def test_exclude_policy_falls_back_to_older_clean_vintage_and_flags_it() -> None:
    # the 09:30 vintage is conflicted -> removed from clean data; 07:30 is used, visibly.
    s = select(utc(2026, 1, 1, 9, 50), without(P_0930), [conflict(P_0930)], "exclude")
    assert s.forecast_mw == 110.0 and s.conflict_fallback and s.conflict_involved


def test_strict_policy_makes_interval_unavailable_when_latest_vintage_is_conflicted() -> None:
    s = select(utc(2026, 1, 1, 9, 50), without(P_0930), [conflict(P_0930)], "strict")
    assert s.forecast_mw is None and s.reason == "conflict"


@pytest.mark.parametrize("policy", ["exclude", "strict"])
def test_conflict_older_than_selected_vintage_is_observable_but_changes_nothing(
    policy: str,
) -> None:
    s = select(utc(2026, 1, 1, 9, 50), without(P_0430), [conflict(P_0430)], policy)
    assert s.forecast_mw == 120.0 and not s.conflict_fallback and s.conflict_involved


def test_conflict_published_after_cutoff_is_irrelevant() -> None:
    s = select(utc(2026, 1, 1, 9, 50), without(P_1130), [conflict(P_1130)], "strict")
    assert s.forecast_mw == 120.0 and not s.conflict_involved


def test_only_conflicted_vintages_means_unavailable_with_reason_conflict() -> None:
    s = select(utc(2026, 1, 1, 9, 50), [], [conflict(P_0730)])
    assert s.forecast_mw is None and s.reason == "conflict"


# ------------------------------------------------------------------ independent oracle
def reference_select(recs, stamp, hour_start, cutoff):  # type: ignore[no-untyped-def]
    """Deliberately naive re-statement of the rule, used as an oracle."""
    cands = [
        r
        for r in recs
        if r.start_utc == stamp
        and r.publish_utc <= cutoff
        and r.publish_utc < hour_start
        and r.mw is not None
    ]
    return max(cands, key=lambda r: r.publish_utc) if cands else None


@pytest.mark.parametrize("seed", range(60))
def test_matches_naive_oracle_on_random_inputs(seed: int) -> None:
    rng = random.Random(seed)
    base = utc(2026, 1, 1)
    stamps = [base + timedelta(hours=h) for h in range(24, 30)]
    recs, seen = [], set()
    for _ in range(rng.randint(0, 40)):
        st = rng.choice(stamps)
        pub = base + timedelta(minutes=rng.randint(0, 60 * 40))
        if (st, pub) in seen:
            continue
        seen.add((st, pub))
        recs.append(ForecastRecord(st, pub, rng.choice([None, 0.0, float(rng.randint(1, 20000))])))
    idx = ForecastIndex(recs)
    for _ in range(25):
        stamp = rng.choice(stamps)
        cutoff = base + timedelta(minutes=rng.randint(0, 60 * 40))
        want = reference_select(recs, stamp, stamp, cutoff)
        got = idx.select(stamp, stamp, cutoff)
        if want is None:
            assert got.forecast_mw is None
        else:
            assert (got.forecast_mw, got.published_at) == (want.mw, want.publish_utc)
