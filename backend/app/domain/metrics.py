"""Accuracy metrics (methodology §4). Pure numpy; all functions take MATCHED pairs only.

error = actual - forecast   (positive: actual exceeded forecast; negative: forecast was too high)
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

QUANTILE_LEVELS = (5, 10, 25, 50, 75, 90, 95)
LOW_COVERAGE_WARN = 0.95
LOW_COVERAGE_STRONG = 0.50


@dataclass(frozen=True, slots=True)
class Metrics:
    """All values are None when n == 0 (never 0 or NaN)."""

    n: int
    mae: float | None
    rmse: float | None
    bias: float | None  # mean signed error
    p90_abs_error: float | None
    error_std: float | None  # population std of error: sqrt(RMSE^2 - bias^2)
    mean_actual: float | None
    mean_forecast: float | None
    nmae: float | None  # MAE / mean_actual, None if mean_actual == 0


EMPTY_METRICS = Metrics(0, None, None, None, None, None, None, None, None)


def coverage(matched: int, expected: int) -> float | None:
    """matched / expected; None when expected == 0 (undefined, never reported as 0 or 1)."""
    return None if expected <= 0 else matched / expected


def coverage_level(cov: float | None) -> str:
    if cov is None:
        return "undefined"
    if cov >= LOW_COVERAGE_WARN:
        return "ok"
    return "partial" if cov >= LOW_COVERAGE_STRONG else "low"


def compute_metrics(actual: Sequence[float], forecast: Sequence[float]) -> Metrics:
    a = np.asarray(actual, dtype=np.float64)
    f = np.asarray(forecast, dtype=np.float64)
    if a.shape != f.shape:
        raise ValueError("actual and forecast must have the same length")
    n = int(a.size)
    if n == 0:
        return EMPTY_METRICS
    if not (np.isfinite(a).all() and np.isfinite(f).all()):
        raise ValueError(
            "metrics require finite matched values; missing values must be excluded first"
        )
    e = a - f
    mae = float(np.mean(np.abs(e)))
    mean_actual = float(np.mean(a))
    return Metrics(
        n=n,
        mae=mae,
        rmse=float(math.sqrt(float(np.mean(e * e)))),
        bias=float(np.mean(e)),
        p90_abs_error=float(np.percentile(np.abs(e), 90, method="linear")),
        error_std=float(np.std(e)),  # ddof=0 -> RMSE^2 = bias^2 + std^2 exactly
        mean_actual=mean_actual,
        mean_forecast=float(np.mean(f)),
        nmae=None if mean_actual == 0 else mae / mean_actual,
    )


@dataclass(frozen=True, slots=True)
class HistogramBin:
    lower: float  # inclusive
    upper: float  # exclusive
    count: int


def error_histogram(errors: Sequence[float], width: float = 500.0) -> list[HistogramBin]:
    """Fixed-width bins anchored at multiples of `width` (stable across filters); half-open [lo, hi)."""
    if width <= 0:
        raise ValueError("bin width must be positive")
    e = np.asarray(errors, dtype=np.float64)
    if e.size == 0:
        return []
    idx = np.floor(e / width).astype(np.int64)
    lo, hi = int(idx.min()), int(idx.max())
    counts = np.bincount(idx - lo, minlength=hi - lo + 1)
    return [
        HistogramBin((lo + i) * width, (lo + i + 1) * width, int(c)) for i, c in enumerate(counts)
    ]


def error_quantiles(errors: Sequence[float]) -> dict[int, float] | None:
    e = np.asarray(errors, dtype=np.float64)
    if e.size == 0:
        return None
    return {q: float(np.percentile(e, q, method="linear")) for q in QUANTILE_LEVELS}


@dataclass(frozen=True, slots=True)
class ExtremeInterval:
    start_utc: datetime
    error_mw: float
    actual_mw: float
    forecast_mw: float


def top_extremes(
    items: Sequence[ExtremeInterval], k: int
) -> tuple[list[ExtremeInterval], list[ExtremeInterval]]:
    """(largest under-forecasts, largest over-forecasts).

    Under-forecast: error > 0 (actual above forecast), descending. Over-forecast: error < 0 (forecast
    too high), most negative first. Zero errors belong to neither. Ties -> earlier start first.
    """
    under = sorted((x for x in items if x.error_mw > 0), key=lambda x: (-x.error_mw, x.start_utc))
    over = sorted((x for x in items if x.error_mw < 0), key=lambda x: (x.error_mw, x.start_utc))
    return under[:k], over[:k]


def elevated_days(
    daily_rmse: dict[object, float], daily_coverage: dict[object, float | None], *,
    percentile: float = 75.0, min_coverage: float = 0.8,
) -> list[object]:  # fmt: skip
    """Days whose RMSE is >= the given percentile of the (sufficiently covered) days' RMSE values."""
    eligible = {
        d: v
        for d, v in daily_rmse.items()
        if (daily_coverage.get(d) or 0.0) >= min_coverage and math.isfinite(v)
    }
    if not eligible:
        return []
    threshold = float(np.percentile(list(eligible.values()), percentile, method="linear"))
    return sorted(d for d, v in eligible.items() if v >= threshold)  # type: ignore[type-var]
