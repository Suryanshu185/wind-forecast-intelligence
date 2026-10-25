"""Parsing, validation and deterministic duplicate / conflict handling (methodology §2).

Rules (see docs/planning/05-analytics-methodology.md):
* All instants are timezone-aware UTC. Naive or non-UTC offsets are rejected.
* ``generation: null`` -> ``mw=None`` (missing). ``0`` stays ``0.0``. Nothing is coerced.
* Exact duplicates collapse. Conflicting duplicates (same key, different value) are
  *removed from the usable data, counted and preserved* in ``conflicts`` - never silently
  resolved by picking a value.
* Output is sorted by key; input order is irrelevant.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.models import (
    ActualRecord,
    Conflict,
    ForecastRecord,
    NormalisationReport,
    NormalisedActuals,
    NormalisedForecasts,
)

LONDON = ZoneInfo("Europe/London")
MAX_REJECTED_EXAMPLES = 5


class RowError(ValueError):
    """A single input row failed validation."""


def parse_utc(value: Any) -> datetime:
    """Parse an ISO-8601 timestamp that carries a UTC designator; return aware UTC datetime."""
    if not isinstance(value, str):
        raise RowError(f"timestamp must be a string, got {type(value).__name__}")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RowError(f"unparseable timestamp {value!r}") from exc
    offset = dt.utcoffset()
    if dt.tzinfo is None or offset is None:
        raise RowError(f"naive timestamp rejected: {value!r}")
    if offset.total_seconds() != 0:
        raise RowError(f"non-UTC offset rejected: {value!r}")
    return dt.astimezone(UTC)


def _parse_mw(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RowError(f"generation must be a number or null, got {value!r}")
    f = float(value)
    if not math.isfinite(f):
        raise RowError(f"non-finite generation {value!r}")
    return f


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise RowError(f"date must be a string, got {type(value).__name__}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RowError(f"unparseable date {value!r}") from exc


def _reject(report: NormalisationReport, message: str) -> None:
    report.rejected_rows += 1
    if len(report.rejected_examples) < MAX_REJECTED_EXAMPLES:
        report.rejected_examples.append(message)


def _sort_values(values: Iterable[float | None]) -> tuple[float | None, ...]:
    uniq = set(values)
    nums = sorted(v for v in uniq if v is not None)
    return (*nums, *([None] if None in uniq else []))


def _count_value(report: NormalisationReport, mw: float | None) -> None:
    if mw is None:
        report.null_generation_rows += 1
    elif mw == 0.0:
        report.zero_generation_rows += 1
    elif mw < 0.0:
        report.negative_value_rows += 1


def normalise_actuals(rows: Iterable[Mapping[str, Any]]) -> NormalisedActuals:
    """Normalise FUELHH rows. Only ``fuelType == 'WIND'`` rows are used."""
    report = NormalisationReport(dataset="FUELHH")
    candidates: dict[datetime, list[ActualRecord]] = defaultdict(list)

    for row in rows:
        report.input_rows += 1
        try:
            if row.get("fuelType") != "WIND":
                report.ignored_other_fuel_rows += 1
                continue
            start = parse_utc(row.get("startTime"))
            publish = parse_utc(row.get("publishTime"))
            mw = _parse_mw(row.get("generation"))
            sdate = _parse_date(row.get("settlementDate"))
            sp = row.get("settlementPeriod")
            if isinstance(sp, bool) or not isinstance(sp, int) or sp < 1:
                raise RowError(f"invalid settlementPeriod {sp!r}")
        except RowError as exc:
            _reject(report, str(exc))
            continue
        if start.minute not in (0, 30) or start.second or start.microsecond:
            report.off_grid_rows += 1
            continue
        if start.astimezone(LONDON).date() != sdate:
            report.settlement_date_mismatches += 1  # kept, but visible
        _count_value(report, mw)
        candidates[start].append(ActualRecord(start, publish, mw, sdate, sp))

    records: list[ActualRecord] = []
    conflicts: list[Conflict] = []
    for start in sorted(candidates):
        group = candidates[start]
        latest = max(r.publish_utc for r in group)
        at_latest = [r for r in group if r.publish_utc == latest]
        report.revisions_superseded += len(group) - len(at_latest)
        values = _sort_values(r.mw for r in at_latest)
        if len(values) > 1:
            conflicts.append(Conflict("FUELHH", start, None, values, len(at_latest)))
            report.conflicting_keys += 1
            report.conflicting_rows += len(at_latest)
            continue
        report.duplicate_rows_collapsed += len(at_latest) - 1
        records.append(at_latest[0])

    report.accepted_rows = len(records)
    return NormalisedActuals(records, conflicts, report)


def normalise_forecasts(rows: Iterable[Mapping[str, Any]]) -> NormalisedForecasts:
    """Normalise WINDFOR rows. Natural key = (startTime, publishTime)."""
    report = NormalisationReport(dataset="WINDFOR")
    candidates: dict[tuple[datetime, datetime], list[ForecastRecord]] = defaultdict(list)

    for row in rows:
        report.input_rows += 1
        try:
            start = parse_utc(row.get("startTime"))
            publish = parse_utc(row.get("publishTime"))
            mw = _parse_mw(row.get("generation"))
        except RowError as exc:
            _reject(report, str(exc))
            continue
        if start.minute != 0 or start.second or start.microsecond:
            report.off_grid_rows += 1
            continue
        _count_value(report, mw)
        candidates[(start, publish)].append(ForecastRecord(start, publish, mw))

    records: list[ForecastRecord] = []
    conflicts: list[Conflict] = []
    for key in sorted(candidates):
        group = candidates[key]
        values = _sort_values(r.mw for r in group)
        if len(values) > 1:
            conflicts.append(Conflict("WINDFOR", key[0], key[1], values, len(group)))
            report.conflicting_keys += 1
            report.conflicting_rows += len(group)
            continue
        report.duplicate_rows_collapsed += len(group) - 1
        records.append(group[0])

    report.accepted_rows = len(records)
    return NormalisedForecasts(records, conflicts, report)
