"""Analysis orchestration: calendar -> point-in-time selection -> matching -> metrics.

Pure and deterministic: (normalised data, config) -> result. No I/O, no framework imports.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal

from app.domain.calendar import (
    HOUR,
    SP,
    cutoff_instant,
    expected_sp_starts_range,
    floor_hour,
    get_zone,
    london_date,
)
from app.domain.metrics import (
    ExtremeInterval,
    HistogramBin,
    Metrics,
    compute_metrics,
    coverage,
    coverage_level,
    elevated_days,
    error_histogram,
    error_quantiles,
    top_extremes,
)
from app.domain.models import NormalisedActuals, NormalisedForecasts
from app.domain.selection import ConflictPolicy, ForecastIndex, Selection

Status = Literal["MATCHED", "FORECAST_UNAVAILABLE", "ACTUAL_MISSING", "BOTH_MISSING"]
Resolution = Literal["half_hour", "hourly"]
Alignment = Literal["start", "end"]


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    delivery_start: date
    delivery_end: date
    cutoff_time: time = time(9, 50)
    cutoff_timezone: str = "Europe/London"
    days_before: int = 1
    availability_lag_minutes: int = 0
    hour_alignment: Alignment = (
        "start"  # ASSUMED, unverified (docs/planning/04-data-research-notes.md s9)
    )
    conflict_policy: ConflictPolicy = "exclude"
    resolution: Resolution = "half_hour"
    top_k: int = 10
    histogram_bin_mw: float = 500.0


@dataclass(frozen=True, slots=True)
class Row:
    """One compared interval: a settlement period (half_hour) or a whole hour (hourly)."""

    start_utc: datetime
    end_utc: datetime
    delivery_date: date
    actual_mw: float | None
    forecast_mw: float | None
    error_mw: float | None  # actual - forecast; None unless MATCHED
    status: Status
    forecast_published_at: datetime | None
    lead_time_h: float | None
    forecast_row_start: datetime  # startTime of the WINDFOR row consulted
    cutoff_utc: datetime  # effective cutoff (after availability lag)
    vintages_total: int
    vintages_eligible: int
    vintages_after_cutoff: int
    unavailable_reason: str | None
    conflict_fallback: bool
    conflict_involved: bool
    actual_conflict: bool


@dataclass(frozen=True, slots=True)
class Counts:
    expected: int
    actual_observed: int
    forecast_available: int
    matched: int
    forecast_unavailable: int
    actual_missing: int
    both_missing: int
    conflict_affected: int  # units where a conflicted record was involved
    coverage: float | None

    @property
    def balanced(self) -> bool:
        return (
            self.matched + self.forecast_unavailable + self.actual_missing + self.both_missing
            == self.expected
        )


@dataclass(frozen=True, slots=True)
class DailyResult:
    delivery_date: date
    counts: Counts
    metrics: Metrics


@dataclass(slots=True)
class AnalysisResult:
    config: AnalysisConfig
    rows: list[Row]  # rows at the configured resolution
    sp_rows: list[Row]  # always the 30-minute rows (basis of the hourly view)
    counts: Counts
    counts_half_hour: Counts
    counts_hourly: Counts
    metrics: Metrics
    daily: list[DailyResult]
    histogram: list[HistogramBin]
    quantiles: dict[int, float] | None
    under_forecasts: list[ExtremeInterval]
    over_forecasts: list[ExtremeInterval]
    elevated_days: list[date]
    over_forecast_count: int
    under_forecast_count: int
    exact_count: int
    coverage_level: str
    partial_hour_sps: int
    unexpected_actual_rows: int
    lead_time_h: dict[str, float] | None
    vintages_used: int
    notes: list[str] = field(default_factory=list)


def effective_cutoff(delivery_date: date, cfg: AnalysisConfig) -> datetime:
    return cutoff_instant(
        delivery_date, cfg.cutoff_time, cfg.days_before, get_zone(cfg.cutoff_timezone)
    ) - timedelta(minutes=cfg.availability_lag_minutes)


def _status(actual: float | None, forecast: float | None) -> Status:
    if actual is not None and forecast is not None:
        return "MATCHED"
    if actual is not None:
        return "FORECAST_UNAVAILABLE"
    if forecast is not None:
        return "ACTUAL_MISSING"
    return "BOTH_MISSING"


def _make_row(
    start: datetime,
    end: datetime,
    d: date,
    actual: float | None,
    actual_conflict: bool,
    sel: Selection,
) -> Row:
    forecast = sel.forecast_mw
    status = _status(actual, forecast)
    return Row(
        start_utc=start,
        end_utc=end,
        delivery_date=d,
        actual_mw=actual,
        forecast_mw=forecast,
        error_mw=(actual - forecast) if actual is not None and forecast is not None else None,
        status=status,
        forecast_published_at=sel.published_at,
        lead_time_h=sel.lead_time_h,
        forecast_row_start=sel.row_stamp,
        cutoff_utc=sel.cutoff_utc,
        vintages_total=sel.vintages_total,
        vintages_eligible=sel.vintages_eligible,
        vintages_after_cutoff=sel.vintages_after_cutoff,
        unavailable_reason=sel.reason,
        conflict_fallback=sel.conflict_fallback,
        conflict_involved=sel.conflict_involved,
        actual_conflict=actual_conflict,
    )


def _counts(rows: list[Row]) -> Counts:
    c = {"MATCHED": 0, "FORECAST_UNAVAILABLE": 0, "ACTUAL_MISSING": 0, "BOTH_MISSING": 0}
    for r in rows:
        c[r.status] += 1
    return Counts(
        expected=len(rows),
        actual_observed=sum(r.actual_mw is not None for r in rows),
        forecast_available=sum(r.forecast_mw is not None for r in rows),
        matched=c["MATCHED"],
        forecast_unavailable=c["FORECAST_UNAVAILABLE"],
        actual_missing=c["ACTUAL_MISSING"],
        both_missing=c["BOTH_MISSING"],
        conflict_affected=sum(
            r.conflict_involved or r.conflict_fallback or r.actual_conflict for r in rows
        ),
        coverage=coverage(c["MATCHED"], len(rows)),
    )


def _matched(rows: list[Row]) -> tuple[list[float], list[float]]:
    a: list[float] = []
    f: list[float] = []
    for r in rows:
        if r.actual_mw is not None and r.forecast_mw is not None:
            a.append(r.actual_mw)
            f.append(r.forecast_mw)
    return a, f


def build_sp_rows(
    actuals: NormalisedActuals, forecasts: NormalisedForecasts, cfg: AnalysisConfig
) -> list[Row]:
    """One row per expected 30-minute settlement period (the expected set comes from the calendar)."""
    expected = expected_sp_starts_range(cfg.delivery_start, cfg.delivery_end)
    actual_by_start = {r.start_utc: r.mw for r in actuals.records}
    actual_conflicts = {c.start_utc for c in actuals.conflicts if c.dataset == "FUELHH"}
    index = ForecastIndex(forecasts.records, forecasts.conflicts)
    cache: dict[tuple[datetime, date], Selection] = {}

    rows: list[Row] = []
    for s in expected:
        d = london_date(s)
        hour_start = floor_hour(s)
        key = (hour_start, d)
        sel = cache.get(key)
        if sel is None:
            # The hour described is always [hour_start, +1h); only the consulted row stamp depends on
            # the (assumed) alignment.
            stamp = hour_start if cfg.hour_alignment == "start" else hour_start + HOUR
            sel = index.select(stamp, hour_start, effective_cutoff(d, cfg), cfg.conflict_policy)
            cache[key] = sel
        in_conflict = s in actual_conflicts
        actual = (
            None if in_conflict else actual_by_start.get(s)
        )  # conflicted actual -> missing, flagged
        rows.append(_make_row(s, s + SP, d, actual, in_conflict, sel))
    return rows


def build_hour_rows(sp_rows: list[Row]) -> tuple[list[Row], int]:
    """Native-hourly rows: actual = mean of both SPs; an hour with a missing half is ACTUAL_MISSING.

    Only whole UTC hours made of two expected SPs are expected hours; stragglers are counted.
    """
    groups: dict[datetime, list[Row]] = defaultdict(list)
    for r in sp_rows:
        groups[floor_hour(r.start_utc)].append(r)
    out: list[Row] = []
    partial = 0
    for hour in sorted(groups):
        g = sorted(groups[hour], key=lambda r: r.start_utc)
        if len(g) != 2:
            partial += len(g)
            continue
        a1, a2 = g[0].actual_mw, g[1].actual_mw
        actual = (a1 + a2) / 2.0 if a1 is not None and a2 is not None else None
        head = g[0]  # both SPs share one selection (same hour, same delivery date)
        forecast = head.forecast_mw
        status = _status(actual, forecast)
        out.append(
            Row(
                start_utc=hour,
                end_utc=hour + HOUR,
                delivery_date=head.delivery_date,
                actual_mw=actual,
                forecast_mw=forecast,
                error_mw=(actual - forecast)
                if actual is not None and forecast is not None
                else None,
                status=status,
                forecast_published_at=head.forecast_published_at,
                lead_time_h=head.lead_time_h,
                forecast_row_start=head.forecast_row_start,
                cutoff_utc=head.cutoff_utc,
                vintages_total=head.vintages_total,
                vintages_eligible=head.vintages_eligible,
                vintages_after_cutoff=head.vintages_after_cutoff,
                unavailable_reason=head.unavailable_reason,
                conflict_fallback=head.conflict_fallback,
                conflict_involved=head.conflict_involved,
                actual_conflict=g[0].actual_conflict or g[1].actual_conflict,
            )
        )
    return out, partial


def run_analysis(
    actuals: NormalisedActuals, forecasts: NormalisedForecasts, cfg: AnalysisConfig
) -> AnalysisResult:
    sp_rows = build_sp_rows(actuals, forecasts, cfg)
    hour_rows, partial = build_hour_rows(sp_rows)
    rows = sp_rows if cfg.resolution == "half_hour" else hour_rows

    counts = _counts(rows)
    a, f = _matched(rows)
    metrics = compute_metrics(a, f)

    by_day: dict[date, list[Row]] = defaultdict(list)
    for r in rows:
        by_day[r.delivery_date].append(r)
    daily: list[DailyResult] = []
    for d in sorted(by_day):
        da, df = _matched(by_day[d])
        daily.append(DailyResult(d, _counts(by_day[d]), compute_metrics(da, df)))

    errors = [r.error_mw for r in rows if r.error_mw is not None]
    extremes_in = [
        ExtremeInterval(r.start_utc, r.error_mw, r.actual_mw, r.forecast_mw)
        for r in rows
        if r.error_mw is not None and r.actual_mw is not None and r.forecast_mw is not None
    ]
    under, over = top_extremes(extremes_in, cfg.top_k)

    flagged = elevated_days(
        {d.delivery_date: d.metrics.rmse for d in daily if d.metrics.rmse is not None},
        {d.delivery_date: d.counts.coverage for d in daily},
    )

    used = [r for r in rows if r.forecast_published_at is not None]
    leads = [r.lead_time_h for r in used if r.lead_time_h is not None]
    expected_set = {r.start_utc for r in sp_rows}
    unexpected = sum(
        1
        for r in actuals.records
        if cfg.delivery_start <= london_date(r.start_utc) <= cfg.delivery_end
        and r.start_utc not in expected_set
    )

    return AnalysisResult(
        config=cfg,
        rows=rows,
        sp_rows=sp_rows,
        counts=counts,
        counts_half_hour=_counts(sp_rows),
        counts_hourly=_counts(hour_rows),
        metrics=metrics,
        daily=daily,
        histogram=error_histogram(errors, cfg.histogram_bin_mw),
        quantiles=error_quantiles(errors),
        under_forecasts=under,
        over_forecasts=over,
        elevated_days=[d for d in flagged if isinstance(d, date)],
        over_forecast_count=sum(e < 0 for e in errors),
        under_forecast_count=sum(e > 0 for e in errors),
        exact_count=sum(e == 0 for e in errors),
        coverage_level=coverage_level(counts.coverage),
        partial_hour_sps=partial,
        unexpected_actual_rows=unexpected,
        lead_time_h=(
            {"min": min(leads), "median": statistics.median(leads), "max": max(leads)}
            if leads
            else None
        ),
        vintages_used=len({r.forecast_published_at for r in used}),
    )
