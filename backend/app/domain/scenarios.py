"""Illustrative uncertainty scenarios from historical forecast errors (methodology §5).

These are ILLUSTRATIVE ANALYTICAL SCENARIOS, not purchase or trading recommendations. There is no demand, contract, other-generation or
price data, so nothing here is a shortfall, an optimal volume, a cost, a saving or a profit.

u = forecast - actual = -error  ("wind under-delivery"; positive when wind came in below the forecast).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.domain.analysis import Row
from app.domain.calendar import LONDON
from app.domain.metrics import Metrics, compute_metrics

DEFAULT_LEVELS = (50, 80, 90, 95)
DISCLAIMER = (
    "Illustrative analytical scenario based on historical forecast errors in a single month. "
    "It is not a purchase or trading recommendation and does not estimate any shortfall, volume, cost or saving."
)


@dataclass(frozen=True, slots=True)
class Buffer:
    confidence_pct: int
    buffer_mw: float  # max(0, Q_c(u))
    raw_quantile_mw: float  # Q_c(u) before clipping at 0 (may be negative)
    energy_mwh_per_sp: float  # unit arithmetic only: 0.5 h * MW


@dataclass(frozen=True, slots=True)
class Band:
    confidence_pct: int
    lower_mw: float
    upper_mw: float


def _levels(levels: Sequence[int]) -> list[int]:
    out = sorted(set(levels))
    if any(not 0 < x < 100 for x in out):
        raise ValueError("confidence levels must be strictly between 0 and 100")
    return out


def underdelivery_buffers(
    errors: Sequence[float], levels: Sequence[int] = DEFAULT_LEVELS
) -> list[Buffer]:
    """Empirical c-quantile of u = -error: "in c% of intervals wind was no more than B MW below forecast"."""
    if not errors:
        return []
    u = -np.asarray(errors, dtype=np.float64)
    out = []
    for c in _levels(levels):
        q = float(np.percentile(u, c, method="linear"))
        b = max(0.0, q)
        out.append(Buffer(c, b, q, 0.5 * b))
    return out


def error_bands(errors: Sequence[float], levels: Sequence[int] = DEFAULT_LEVELS) -> list[Band]:
    """Central empirical interval of the signed error for each confidence level."""
    if not errors:
        return []
    e = np.asarray(errors, dtype=np.float64)
    out = []
    for c in _levels(levels):
        lo = float(np.percentile(e, (100 - c) / 2, method="linear"))
        hi = float(np.percentile(e, 100 - (100 - c) / 2, method="linear"))
        out.append(Band(c, lo, hi))
    return out


@dataclass(frozen=True, slots=True)
class Bucket:
    label: str
    sort_key: float
    metrics: Metrics


def _matched(rows: Sequence[Row]) -> list[Row]:
    return [r for r in rows if r.error_mw is not None and r.forecast_mw is not None]


def _bucketise(rows: Sequence[Row], keyfn, labelfn) -> list[Bucket]:  # type: ignore[no-untyped-def]
    groups: dict[float, list[Row]] = defaultdict(list)
    for r in _matched(rows):
        groups[keyfn(r)].append(r)
    out = []
    for k in sorted(groups):
        g = groups[k]
        out.append(
            Bucket(
                labelfn(k),
                k,
                compute_metrics([r.actual_mw for r in g], [r.forecast_mw for r in g]),  # type: ignore[misc]
            )
        )
    return out


def by_hour_of_day(rows: Sequence[Row]) -> list[Bucket]:
    """Metrics per London local hour of day (0-23) of the delivery interval start."""
    return _bucketise(
        rows, lambda r: float(r.start_utc.astimezone(LONDON).hour), lambda k: f"{int(k):02d}:00"
    )


def by_lead_time(rows: Sequence[Row], bucket_h: int = 6) -> list[Bucket]:
    """Metrics per lead-time bucket of the selected vintage (hours between publish and delivery hour)."""
    if bucket_h <= 0:
        raise ValueError("bucket_h must be positive")
    return _bucketise(
        rows,
        lambda r: float(math.floor((r.lead_time_h or 0.0) / bucket_h) * bucket_h),
        lambda k: f"{int(k)}-{int(k) + bucket_h} h",
    )


def by_forecast_level(rows: Sequence[Row], n_bins: int = 3) -> list[Bucket]:
    """Metrics per forecast-level tercile (equal-count bins by forecast MW)."""
    m = _matched(rows)
    if not m:
        return []
    order = sorted(m, key=lambda r: (r.forecast_mw, r.start_utc))
    size = math.ceil(len(order) / n_bins)
    out = []
    for i in range(n_bins):
        g = order[i * size : (i + 1) * size]
        if not g:
            continue
        lo, hi = g[0].forecast_mw, g[-1].forecast_mw
        out.append(
            Bucket(
                f"{lo:,.0f}-{hi:,.0f} MW forecast",
                float(i),
                compute_metrics([r.actual_mw for r in g], [r.forecast_mw for r in g]),  # type: ignore[misc]
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class RollingDay:
    delivery_date: date
    history_days: int
    buffer_mw: float
    n: int
    within_buffer: int


@dataclass(frozen=True, slots=True)
class RollingOrigin:
    confidence_pct: int
    days: list[RollingDay]
    skipped_days: int  # not enough history
    realised_pct: float | None  # share of evaluated intervals with u <= buffer


def rolling_origin(
    rows: Sequence[Row], confidence_pct: int, min_history_days: int = 7
) -> RollingOrigin:
    """Honest out-of-sample check of the buffer idea.

    For delivery day D, the buffer is computed ONLY from delivery days <= D-2 (final actuals for D-1 are not
    complete at a D-1 morning decision), then compared with what happened on D.
    """
    by_day: dict[date, list[float]] = defaultdict(list)
    for r in _matched(rows):
        by_day[r.delivery_date].append(-r.error_mw)  # type: ignore[operator]  # u = -error
    days = sorted(by_day)
    out: list[RollingDay] = []
    skipped = 0
    for d in days:
        hist_days = [h for h in days if h <= d - timedelta(days=2)]
        if len(hist_days) < min_history_days:
            skipped += 1
            continue
        hist = np.concatenate([np.asarray(by_day[h]) for h in hist_days])
        b = max(0.0, float(np.percentile(hist, confidence_pct, method="linear")))
        today = by_day[d]
        out.append(RollingDay(d, len(hist_days), b, len(today), sum(u <= b for u in today)))
    total = sum(x.n for x in out)
    realised = None if total == 0 else 100.0 * sum(x.within_buffer for x in out) / total
    return RollingOrigin(confidence_pct, out, skipped, realised)
