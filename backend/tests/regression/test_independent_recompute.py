"""Independent end-to-end recomputation from the RAW committed snapshot files.

This re-implements the selection rule and metrics with the standard library only (csv/gzip/datetime/statistics),
sharing NO code with `app.domain`, and compares the result with what the HTTP API returns. It proves that every
displayed number is derived from the real snapshot, for the 30-minute view, the native-hourly view and the
(unverified) alternative hour alignment. January has no DST, so Europe/London == UTC for these dates.
"""

from __future__ import annotations

import csv
import gzip
import math
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

FMT = "%Y-%m-%dT%H:%M:%SZ"


def _z(s: str) -> datetime:
    return datetime.strptime(s, FMT).replace(tzinfo=UTC)


@pytest.fixture(scope="module")
def raw() -> tuple[dict[datetime, float], dict[datetime, list[tuple[datetime, float]]]]:
    d: Path = get_settings().data_snapshot_dir
    with gzip.open(d / "fuelhh_wind.csv.gz", "rt", newline="") as f:
        actual = {_z(r["startTime"]): float(r["generation"]) for r in csv.DictReader(f)}
    fc: dict[datetime, list[tuple[datetime, float]]] = defaultdict(list)
    with gzip.open(d / "windfor.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            fc[_z(r["startTime"])].append((_z(r["publishTime"]), float(r["generation"])))
    return actual, fc


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app(get_settings())) as c:
        yield c


def metrics(errs: list[float]) -> dict[str, float]:
    n = len(errs)
    absE = sorted(abs(e) for e in errs)
    pos = 0.9 * (n - 1)
    lo = math.floor(pos)
    p90 = absE[lo] + (pos - lo) * (absE[min(lo + 1, n - 1)] - absE[lo])
    return {
        "n": n,
        "mae": sum(absE) / n,
        "rmse": math.sqrt(sum(e * e for e in errs) / n),
        "bias": sum(errs) / n,
        "p90_abs_error": p90,
    }


def expected(
    raw,
    *,
    cutoff_h: int,
    cutoff_m: int,
    lag: int,
    align: str,
    resolution: str,
    d0: int = 1,
    d1: int = 31,
):  # type: ignore[no-untyped-def]
    actual, fc = raw

    def forecast_for(hour_start: datetime) -> float | None:
        day = hour_start.replace(hour=0, minute=0)
        cutoff = (day - timedelta(days=1)).replace(hour=cutoff_h, minute=cutoff_m) - timedelta(
            minutes=lag
        )
        stamp = hour_start if align == "start" else hour_start + timedelta(hours=1)
        ok = [(p, v) for p, v in fc.get(stamp, []) if p <= cutoff and p < hour_start]
        return max(ok)[1] if ok else None

    errs: list[float] = []
    total = 0
    for day in range(d0, d1 + 1):
        for h in range(24):
            hs = datetime(2026, 1, day, h, tzinfo=UTC)
            f = forecast_for(hs)
            halves = [actual.get(hs), actual.get(hs + timedelta(minutes=30))]
            if resolution == "hourly":
                total += 1
                if f is not None and None not in halves:
                    errs.append(sum(halves) / 2 - f)  # type: ignore[arg-type]
            else:
                for a in halves:
                    total += 1
                    if f is not None and a is not None:
                        errs.append(a - f)
    return metrics(errs), total


CASES = [
    dict(cutoff_h=9, cutoff_m=50, lag=0, align="start", resolution="half_hour"),
    dict(cutoff_h=9, cutoff_m=20, lag=0, align="start", resolution="half_hour"),
    dict(cutoff_h=15, cutoff_m=30, lag=0, align="start", resolution="half_hour"),
    dict(cutoff_h=9, cutoff_m=50, lag=21, align="start", resolution="half_hour"),
    dict(cutoff_h=9, cutoff_m=50, lag=0, align="end", resolution="half_hour"),
    dict(cutoff_h=9, cutoff_m=50, lag=0, align="start", resolution="hourly"),
    dict(cutoff_h=9, cutoff_m=50, lag=0, align="end", resolution="hourly"),
    dict(cutoff_h=12, cutoff_m=30, lag=15, align="end", resolution="hourly"),
]


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda c: (
        f"{c['cutoff_h']:02d}{c['cutoff_m']:02d}-lag{c['lag']}-{c['align']}-{c['resolution']}"
    ),
)
def test_api_equals_independent_recomputation_from_raw_snapshot(
    client: TestClient, raw: Any, case: dict[str, Any]
) -> None:
    want, total = expected(raw, **case)
    r = client.get(
        "/api/v1/analysis/summary",
        params={
            "cutoff_time": f"{case['cutoff_h']:02d}:{case['cutoff_m']:02d}",
            "availability_lag_minutes": case["lag"],
            "hour_alignment": case["align"],
            "resolution": case["resolution"],
        },
    )
    got = r.json()
    assert got["counts"]["expected"] == total
    assert got["counts"]["matched"] == want["n"] == got["metrics"]["n"]
    for k in ("mae", "rmse", "bias", "p90_abs_error"):
        assert got["metrics"][k] == pytest.approx(want[k], rel=1e-9, abs=1e-6), k


def test_sub_range_matches_independent_recomputation(client: TestClient, raw: Any) -> None:
    want, total = expected(
        raw, cutoff_h=9, cutoff_m=50, lag=0, align="start", resolution="half_hour", d0=12, d1=14
    )
    got = client.get(
        "/api/v1/analysis/summary",
        params={"delivery_start": "2026-01-12", "delivery_end": "2026-01-14"},
    ).json()
    assert got["counts"]["expected"] == total == 144
    assert got["metrics"]["mae"] == pytest.approx(want["mae"], rel=1e-9)


def test_alignment_end_and_hourly_views_differ_from_default_and_are_labelled(
    client: TestClient,
) -> None:
    base = client.get("/api/v1/analysis/summary").json()
    end = client.get("/api/v1/analysis/summary", params={"hour_alignment": "end"}).json()
    hourly = client.get("/api/v1/analysis/summary", params={"resolution": "hourly"}).json()
    assert base["alignment"]["status"] == end["alignment"]["status"] == "assumed"
    assert (
        "unverified" in base["alignment"]["note"].lower()
        and "unverified" in end["alignment"]["note"].lower()
    )
    assert end["metrics"]["mae"] != base["metrics"]["mae"]
    assert hourly["counts"]["unit"] == "hours" and hourly["counts"]["expected"] == 744
    assert (
        "NOT independent" in base["resolution_note"] and "never filled" in hourly["resolution_note"]
    )
