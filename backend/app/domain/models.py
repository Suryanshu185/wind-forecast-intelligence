"""Typed domain records. Pure data - no I/O, no framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

DatasetName = Literal["FUELHH", "WINDFOR"]


@dataclass(frozen=True, slots=True)
class ActualRecord:
    """One FUELHH WIND settlement period. `mw is None` means *missing*, never zero."""

    start_utc: datetime
    publish_utc: datetime
    mw: float | None
    settlement_date: date
    settlement_period: int


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    """One WINDFOR row (hourly forecast vintage). `mw is None` means *missing*."""

    start_utc: datetime
    publish_utc: datetime
    mw: float | None


@dataclass(frozen=True, slots=True)
class Conflict:
    """Records sharing a natural key but disagreeing on value.

    Conflicting rows are removed from the usable data but preserved here so that they
    remain observable (counted, listed in data-quality output, flagged on affected intervals).
    """

    dataset: DatasetName
    start_utc: datetime
    publish_utc: datetime | None  # None for actuals keyed on start only
    values: tuple[float | None, ...]  # distinct values, ascending (None last)
    row_count: int


@dataclass(slots=True)
class NormalisationReport:
    """Counters describing everything normalisation did. Nothing is dropped silently."""

    dataset: DatasetName
    input_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    ignored_other_fuel_rows: int = 0
    off_grid_rows: int = 0
    null_generation_rows: int = 0
    zero_generation_rows: int = 0
    negative_value_rows: int = 0
    duplicate_rows_collapsed: int = 0
    conflicting_keys: int = 0
    conflicting_rows: int = 0
    revisions_superseded: int = 0
    settlement_date_mismatches: int = 0
    rejected_examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset,
            "input_rows": self.input_rows,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "ignored_other_fuel_rows": self.ignored_other_fuel_rows,
            "off_grid_rows": self.off_grid_rows,
            "null_generation_rows": self.null_generation_rows,
            "zero_generation_rows": self.zero_generation_rows,
            "negative_value_rows": self.negative_value_rows,
            "duplicate_rows_collapsed": self.duplicate_rows_collapsed,
            "conflicting_keys": self.conflicting_keys,
            "conflicting_rows": self.conflicting_rows,
            "revisions_superseded": self.revisions_superseded,
            "settlement_date_mismatches": self.settlement_date_mismatches,
            "rejected_examples": list(self.rejected_examples),
        }


@dataclass(slots=True)
class NormalisedActuals:
    records: list[ActualRecord]
    conflicts: list[Conflict]
    report: NormalisationReport


@dataclass(slots=True)
class NormalisedForecasts:
    records: list[ForecastRecord]
    conflicts: list[Conflict]
    report: NormalisationReport
