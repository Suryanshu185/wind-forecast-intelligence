#!/usr/bin/env python3
"""Throw-away research probe for the planning phase. NOT application code.

Purpose: reproduce the structural facts recorded in docs/planning/04-data-research-notes.md
directly from the live Elexon Insights API, using only the Python standard library.

Usage:  python3 docs/planning/research/probe_elexon.py
Output: plain text to stdout. Downloads go to a temp dir and are not kept in the repo.

All numbers printed here come from real API responses retrieved at run time.
The "cutoff sensitivity" table is an exploratory calculation (hourly forecast step-held
across both half-hours, errors = actual - forecast) and is NOT the production algorithm.
"""
from __future__ import annotations

import collections as C
import json
import math
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def get(path: str, **params: str) -> list[dict]:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params, safe=':')}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (public https API)
        return json.load(resp)


def p(s: str) -> datetime:
    return datetime.strptime(s, FMT).replace(tzinfo=timezone.utc)


def f(d: datetime) -> str:
    return d.strftime(FMT)


def main() -> None:
    retrieved = datetime.now(timezone.utc).strftime(FMT)
    print(f"# Retrieved (UTC): {retrieved}")
    fh = get("/datasets/FUELHH/stream", settlementDateFrom="2026-01-01",
             settlementDateTo="2026-01-31", fuelType="WIND")
    wf = get("/datasets/WINDFOR/stream", publishDateTimeFrom="2025-12-27T00:00:00Z",
             publishDateTimeTo="2026-02-04T00:00:00Z")
    tmp = tempfile.mkdtemp(prefix="elexon_probe_")
    print(f"# temp dir (not in repo): {tmp}")

    print("\n== FUELHH (WIND, settlement dates 2026-01-01..2026-01-31)")
    print("rows:", len(fh), "| keys:", sorted(fh[0]))
    print("distinct startTime:", len({r["startTime"] for r in fh}), "(expected 31*48 = 1488)")
    print("startTime minutes:", dict(C.Counter(p(r["startTime"]).minute for r in fh)))
    print("settlement periods per date:", set(C.Counter(r["settlementDate"] for r in fh).values()))
    print("null generation:", sum(r["generation"] is None for r in fh),
          "| zero:", sum(r["generation"] == 0 for r in fh),
          "| min/max MW:", min(r["generation"] for r in fh), max(r["generation"] for r in fh))
    lag = C.Counter((p(r["publishTime"]) - p(r["startTime"])).total_seconds() / 60 for r in fh)
    print("publishTime - startTime (minutes) distribution:", dict(lag))

    print("\n== WINDFOR (publishTime 2025-12-27 .. 2026-02-04)")
    print("rows:", len(wf), "| keys:", sorted(wf[0]))
    print("startTime minutes:", dict(C.Counter(p(r["startTime"]).minute for r in wf)),
          "<- hourly resolution if only {0}")
    pubs = C.defaultdict(list)
    for r in wf:
        pubs[r["publishTime"]].append(r)
    print("distinct publishTime (vintages):", len(pubs),
          "| rows per vintage:", dict(C.Counter(len(v) for v in pubs.values())))
    print("publish clock times (UTC):", sorted(dict(C.Counter(k[11:16] for k in pubs)).items()))
    print("duplicate (startTime, publishTime) keys:",
          sum(1 for c in C.Counter((r["startTime"], r["publishTime"]) for r in wf).values() if c > 1))
    print("null generation:", sum(r["generation"] is None for r in wf),
          "| zero:", sum(r["generation"] == 0 for r in wf))
    hz = [(p(r["startTime"]) - p(r["publishTime"])).total_seconds() / 3600 for r in wf]
    print(f"horizon (startTime - publishTime) hours: min {min(hz)}, max {max(hz)} "
          "(negative => forecast published after the interval began)")
    slots = ["02:30", "04:30", "07:30", "09:30", "11:30", "15:30", "18:30", "22:30"]
    d, missing = datetime(2025, 12, 27), []
    while d < datetime(2026, 2, 4):
        for s in slots:
            k = f"{d:%Y-%m-%d}T{s}:00Z"
            if k not in pubs:
                missing.append(k)
        d += timedelta(days=1)
    print("nominal winter publish slots absent:", missing)
    print("off-schedule publishTimes:", [k for k in pubs if k[11:16] not in slots])

    # ---- exploratory cutoff sensitivity -----------------------------------------------
    by_start = C.defaultdict(list)
    for r in wf:
        by_start[r["startTime"]].append(r)
    actual = {r["startTime"]: r["generation"] for r in fh}

    def simulate(h: int, m: int) -> str:
        errs, hours_avail, hours_total, horizons = [], 0, 0, []
        day = datetime(2026, 1, 1, tzinfo=timezone.utc)  # Jan: Europe/London == UTC
        while day < datetime(2026, 2, 1, tzinfo=timezone.utc):
            cutoff = (day - timedelta(days=1)).replace(hour=h, minute=m)
            for hh in range(24):
                st = day + timedelta(hours=hh)
                hours_total += 1
                el = [r for r in by_start.get(f(st), []) if p(r["publishTime"]) <= cutoff]
                if not el:
                    continue
                hours_avail += 1
                best = max(el, key=lambda r: r["publishTime"])
                horizons.append((st - p(best["publishTime"])).total_seconds() / 3600)
                for off in (0, 30):
                    a = actual.get(f(st + timedelta(minutes=off)))
                    if a is not None:
                        errs.append(a - best["generation"])
            day += timedelta(days=1)
        ae = sorted(abs(e) for e in errs)
        n = len(errs)
        return (f"avail {hours_avail}/{hours_total}h-slots, matched {n}/1488 SP | "
                f"MAE {sum(ae)/n:.0f} RMSE {math.sqrt(sum(e*e for e in errs)/n):.0f} "
                f"bias {sum(errs)/n:.0f} MW | lead {min(horizons)}-{max(horizons)} h")

    print("\n== Exploratory: cutoff sensitivity (decision day = delivery date - 1, clock time in UTC=London)")
    for h, m in [(9, 20), (9, 50), (12, 0), (15, 30), (23, 59)]:
        print(f"cutoff {h:02d}:{m:02d}: {simulate(h, m)}")

    # ---- DST day lengths in FUELHH ----------------------------------------------------
    print("\n== FUELHH settlement periods on clock-change days (2025)")
    for day, label in [("2025-03-30", "spring forward"), ("2025-10-26", "autumn back")]:
        rows = get("/datasets/FUELHH/stream", settlementDateFrom=day, settlementDateTo=day, fuelType="WIND")
        print(f"{day} ({label}): {len(rows)} rows, max settlementPeriod {max(r['settlementPeriod'] for r in rows)}, "
              f"startTime {min(r['startTime'] for r in rows)} .. {max(r['startTime'] for r in rows)}")


if __name__ == "__main__":
    main()
