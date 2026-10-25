"""Normalisation tests. All inputs here are SYNTHETIC, hand-built rows (not Elexon observations)."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.normalise import RowError, normalise_actuals, normalise_forecasts, parse_utc


def synthetic_actual(
    start: str, mw: Any, publish: str | None = None, **over: Any
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "dataset": "FUELHH",
        "fuelType": "WIND",
        "startTime": start,
        "publishTime": publish or start,
        "settlementDate": start[:10],
        "settlementPeriod": 1,
        "generation": mw,
    }
    row.update(over)
    return row


def synthetic_forecast(start: str, publish: str, mw: Any) -> dict[str, Any]:
    return {"dataset": "WINDFOR", "startTime": start, "publishTime": publish, "generation": mw}


# ---------------------------------------------------------------- timestamp parsing
def test_parse_utc_accepts_z_and_zero_offset() -> None:
    expected = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
    assert parse_utc("2026-01-01T09:30:00Z") == expected
    assert parse_utc("2026-01-01T09:30:00+00:00") == expected
    assert parse_utc("2026-01-01T09:30:00Z").tzinfo is not None


@pytest.mark.parametrize(
    "bad",
    ["2026-01-01T09:30:00", "2026-01-01T09:30:00+01:00", "not a date", "", 12345, None],
)
def test_parse_utc_rejects_naive_offset_and_garbage(bad: Any) -> None:
    with pytest.raises(RowError):
        parse_utc(bad)


# ---------------------------------------------------------------- missing vs zero
def test_null_is_missing_and_zero_is_preserved() -> None:
    res = normalise_actuals(
        [
            synthetic_actual("2026-01-01T00:00:00Z", None),
            synthetic_actual("2026-01-01T00:30:00Z", 0, settlementPeriod=2),
        ]
    )
    by_start = {r.start_utc.minute: r for r in res.records}
    assert by_start[0].mw is None
    assert by_start[30].mw == 0.0 and by_start[30].mw is not None
    assert res.report.null_generation_rows == 1
    assert res.report.zero_generation_rows == 1


def test_negative_values_are_kept_and_counted() -> None:
    res = normalise_forecasts(
        [synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", -5)]
    )
    assert res.records[0].mw == -5.0
    assert res.report.negative_value_rows == 1


# ---------------------------------------------------------------- rejection and filtering
def test_rejected_rows_are_counted_with_examples_not_silently_dropped() -> None:
    res = normalise_forecasts(
        [
            synthetic_forecast("2026-01-01T01:00:00", "2025-12-31T22:30:00Z", 1),  # naive
            synthetic_forecast(
                "2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", "abc"
            ),  # non-numeric
            synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", True),  # bool
            synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 100),  # ok
        ]
    )
    assert res.report.input_rows == 4
    assert res.report.rejected_rows == 3
    assert res.report.accepted_rows == 1
    assert len(res.report.rejected_examples) == 3


def test_off_grid_forecast_rows_excluded_and_counted() -> None:
    res = normalise_forecasts(
        [synthetic_forecast("2026-01-01T01:30:00Z", "2025-12-31T22:30:00Z", 100)]
    )
    assert res.records == []
    assert res.report.off_grid_rows == 1


def test_actual_off_grid_and_other_fuels() -> None:
    res = normalise_actuals(
        [
            synthetic_actual("2026-01-01T00:15:00Z", 10),
            synthetic_actual("2026-01-01T00:00:00Z", 10, fuelType="NUCLEAR"),
            synthetic_actual("2026-01-01T00:00:00Z", 10),
        ]
    )
    assert len(res.records) == 1
    assert res.report.off_grid_rows == 1
    assert res.report.ignored_other_fuel_rows == 1


def test_settlement_date_mismatch_is_counted_but_row_kept() -> None:
    res = normalise_actuals(
        [synthetic_actual("2026-01-01T00:00:00Z", 10, settlementDate="2026-01-02")]
    )
    assert len(res.records) == 1
    assert res.report.settlement_date_mismatches == 1


def test_settlement_date_uses_london_local_date_in_summer() -> None:
    # 23:30Z on 30 June is 00:30 BST on 1 July -> settlementDate 2025-07-01 is consistent.
    res = normalise_actuals(
        [synthetic_actual("2025-06-30T23:30:00Z", 10, settlementDate="2025-07-01")]
    )
    assert res.report.settlement_date_mismatches == 0


# ---------------------------------------------------------------- duplicates & conflicts
def test_exact_duplicate_forecasts_collapse_and_are_counted() -> None:
    row = synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 500)
    res = normalise_forecasts([row, dict(row), dict(row)])
    assert len(res.records) == 1
    assert res.report.duplicate_rows_collapsed == 2
    assert res.conflicts == []


def test_conflicting_forecasts_are_removed_preserved_and_counted_never_resolved() -> None:
    rows = [
        synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 500),
        synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 700),
        synthetic_forecast("2026-01-01T02:00:00Z", "2025-12-31T22:30:00Z", 600),
    ]
    res = normalise_forecasts(rows)
    assert [r.mw for r in res.records] == [600.0]  # neither 500 nor 700 survives
    assert len(res.conflicts) == 1
    c = res.conflicts[0]
    assert c.values == (500.0, 700.0) and c.row_count == 2 and c.dataset == "WINDFOR"
    assert (res.report.conflicting_keys, res.report.conflicting_rows) == (1, 2)


def test_null_versus_number_is_a_conflict() -> None:
    rows = [
        synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", None),
        synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 0),
    ]
    res = normalise_forecasts(rows)
    assert res.records == []
    assert res.conflicts[0].values == (0.0, None)


def test_same_start_different_publish_forecasts_are_distinct_vintages_not_duplicates() -> None:
    res = normalise_forecasts(
        [
            synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 500),
            synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T18:30:00Z", 700),
        ]
    )
    assert len(res.records) == 2 and res.conflicts == []


def test_actual_revisions_keep_latest_publish() -> None:
    res = normalise_actuals(
        [
            synthetic_actual("2026-01-01T00:00:00Z", 100, publish="2026-01-01T00:30:00Z"),
            synthetic_actual("2026-01-01T00:00:00Z", 110, publish="2026-01-01T02:00:00Z"),
        ]
    )
    assert [r.mw for r in res.records] == [110.0]
    assert res.report.revisions_superseded == 1


def test_actual_conflict_at_same_publish_is_preserved_not_resolved() -> None:
    res = normalise_actuals(
        [
            synthetic_actual("2026-01-01T00:00:00Z", 100, publish="2026-01-01T00:30:00Z"),
            synthetic_actual("2026-01-01T00:00:00Z", 105, publish="2026-01-01T00:30:00Z"),
        ]
    )
    assert res.records == []
    assert res.conflicts[0].values == (100.0, 105.0)


def test_result_is_independent_of_input_order() -> None:
    rows = [
        synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 500),
        synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 700),  # conflict
        synthetic_forecast("2026-01-01T02:00:00Z", "2025-12-31T22:30:00Z", 600),
        synthetic_forecast("2026-01-01T02:00:00Z", "2025-12-31T22:30:00Z", 600),  # exact dup
        synthetic_forecast("2026-01-01T03:00:00Z", "2025-12-31T18:30:00Z", 650),
    ]
    baseline = normalise_forecasts(rows)
    for perm in itertools.islice(itertools.permutations(rows), 40):
        got = normalise_forecasts(perm)
        assert got.records == baseline.records
        assert got.conflicts == baseline.conflicts
        assert got.report.as_dict() == baseline.report.as_dict()


def test_output_sorted_by_key() -> None:
    res = normalise_forecasts(
        [
            synthetic_forecast("2026-01-01T03:00:00Z", "2025-12-31T22:30:00Z", 3),
            synthetic_forecast("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 1),
        ]
    )
    assert [r.mw for r in res.records] == [1.0, 3.0]
