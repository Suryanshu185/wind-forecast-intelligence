#!/usr/bin/env python3
"""Pre-implementation investigation B (and supporting evidence for A). NOT application code.

Question: why does WINDFOR (day-ahead vintage) exceed FUELHH WIND outturn by ~1.8 GW on average?

Method (all real data, stdlib only, public API, no key):
  1. Units / scale sanity: FUELHH vs an independent BMRS actual-wind series (B1630 "AGWS":
     /generation/actual/per-type/wind-and-solar, Wind Onshore + Wind Offshore).
  2. Persistence by month (Oct 2025 - Jan 2026) and by output level.
  3. Bias of the selected WINDFOR vintage against each actual series.
  4. Bias vs forecast lead time (is it a cutoff/vintage artefact?).
  5. Bias under the two possible hour alignments (reported as a sensitivity, NOT used to choose one).

AGWS is used here ONLY as a diagnostic cross-reference. It is not part of the application's core analysis.
Usage: python3 docs/planning/research/probe_bias_investigation.py
"""
from __future__ import annotations

import collections as C
import json
import math
import statistics as S
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def get(path: str, **q: str):
    url = BASE + path + "?" + urllib.parse.urlencode(q, safe=":")
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310
        return json.load(r)


p = lambda s: datetime.strptime(s, FMT).replace(tzinfo=timezone.utc)  # noqa: E731
f = lambda d: d.strftime(FMT)  # noqa: E731


def main() -> None:
    print("# retrieved (UTC):", f(datetime.now(timezone.utc)))
    fh = {r["startTime"]: r["generation"] for r in get(
        "/datasets/FUELHH/stream", settlementDateFrom="2025-10-01", settlementDateTo="2026-01-31", fuelType="WIND")}
    wf = get("/datasets/WINDFOR/stream", publishDateTimeFrom="2025-09-27T00:00:00Z", publishDateTimeTo="2026-02-04T00:00:00Z")
    ag: dict = {}
    d, end = datetime(2025, 10, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc)
    while d < end:  # AGWS endpoint limit: range must not exceed 7 days inclusive
        e = min(d + timedelta(days=6), end)
        for r in get("/generation/actual/per-type/wind-and-solar", **{"from": f(d), "to": f(e), "format": "json"})["data"]:
            if "Wind" in r["psrType"]:
                k = (r["psrType"], r["startTime"])
                if k not in ag or ag[k]["publishTime"] < r["publishTime"]:
                    ag[k] = r
        d = e
    agt: dict[str, float] = C.defaultdict(float)
    agc: C.Counter = C.Counter()
    for (_, st), r in ag.items():
        agt[st] += r["quantity"]
        agc[st] += 1

    idx = C.defaultdict(list)
    for r in wf:
        idx[r["startTime"]].append(r)

    def select(sp_start: str, h: int = 9, m: int = 50, alignment: str = "begin"):
        t = p(sp_start)
        hour = t.replace(minute=0)
        slot = hour if alignment == "begin" else hour + timedelta(hours=1)
        day = t.replace(hour=0, minute=0)  # January: London == UTC
        cutoff = (day - timedelta(days=1)).replace(hour=h, minute=m)
        el = [r for r in idx.get(f(slot), []) if p(r["publishTime"]) <= cutoff and p(r["publishTime"]) < t]
        if not el:
            return None, None
        best = max(el, key=lambda r: r["publishTime"])
        return best["generation"], (slot - p(best["publishTime"])).total_seconds() / 3600

    print("\n== 1. Scale / units: FUELHH WIND vs B1630 (onshore+offshore), same SP")
    rows = [(s, fh[s], agt[s]) for s in fh if agc.get(s) == 2]
    ratio = [a / b for _, a, b in rows]
    diff = [b - a for _, a, b in rows]
    print(f"n={len(rows)} | mean FUELHH {S.mean(a for _, a, _ in rows):.0f} MW | mean B1630 {S.mean(b for *_, b in rows):.0f} MW")
    print(f"ratio FUELHH/B1630: mean {S.mean(ratio):.3f} sd {S.pstdev(ratio):.3f} min {min(ratio):.3f} max {max(ratio):.3f}"
          "  (a MW-vs-MWh unit error would give ~0.5 or ~2.0)")
    print(f"share of SPs with FUELHH < B1630: {sum(a < b for _, a, b in rows) / len(rows):.4f}")
    print(f"B1630 - FUELHH (MW): mean {S.mean(diff):.0f} sd {S.pstdev(diff):.0f} min {min(diff):.0f} max {max(diff):.0f}")

    print("\n== 2/3. By month: selected WINDFOR (cutoff 09:50 D-1, hour-beginning) vs each actual series (MW)")
    print("month | n | FUELHH | B1630 | WINDFOR | FUELHH-B1630 | bias vs FUELHH | bias vs B1630")
    for mon in ("2025-10", "2025-11", "2025-12", "2026-01"):
        tr = []
        for s in fh:
            if s.startswith(mon) and agc.get(s) == 2:
                w, _ = select(s)
                if w is not None:
                    tr.append((fh[s], agt[s], w))
        mm = lambda i: S.mean(x[i] for x in tr)  # noqa: E731
        print(f"{mon} | {len(tr)} | {mm(0):.0f} | {mm(1):.0f} | {mm(2):.0f} | {mm(0) - mm(1):.0f} | {mm(0) - mm(2):.0f} | {mm(1) - mm(2):.0f}")

    jan = [(s, fh[s], agt[s], select(s)[0]) for s in fh if s.startswith("2026-01") and agc.get(s) == 2 and select(s)[0] is not None]
    for name, i in (("FUELHH", 1), ("B1630", 2)):
        e = [r[i] - r[3] for r in jan]
        print(f"Jan: WINDFOR vs {name}: n={len(e)} MAE {S.mean(map(abs, e)):.0f} RMSE {math.sqrt(S.mean(x * x for x in e)):.0f} bias {S.mean(e):.0f}")
    jr = sorted(jan, key=lambda r: r[1])
    n = len(jr)
    for k, (a, b) in enumerate(((0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n))):
        seg = jr[a:b]
        print(f"  FUELHH-level tercile {k + 1}: mean {S.mean(x[1] for x in seg):.0f} | bias vs FUELHH {S.mean(x[1] - x[3] for x in seg):.0f}"
              f" | bias vs B1630 {S.mean(x[2] - x[3] for x in seg):.0f}")

    print("\n== 4. Bias vs lead time of ALL vintages (Jan, vs FUELHH hourly mean) - is it a cutoff artefact?")
    buckets = C.defaultdict(list)
    for st, rs in idx.items():
        if not st.startswith("2026-01"):
            continue
        halves = [fh.get(f(p(st) + timedelta(minutes=m))) for m in (0, 30)]
        if None in halves:
            continue
        for r in rs:
            lead = (p(st) - p(r["publishTime"])).total_seconds() / 3600
            buckets[int(lead // 12) * 12].append(sum(halves) / 2 - r["generation"])
    for b in sorted(buckets):
        print(f"  lead [{b},{b + 12}) h: n={len(buckets[b])} bias {S.mean(buckets[b]):.0f} MW")

    print("\n== 5. Alignment sensitivity of the MEAN bias vs FUELHH (reported only; NOT used to choose an alignment)")
    for al in ("begin", "end"):
        e = []
        for s in fh:
            if s.startswith("2026-01"):
                w, _ = select(s, alignment=al)
                if w is not None:
                    e.append(fh[s] - w)
        print(f"  hour-{al}ning mapping: n={len(e)} bias {S.mean(e):.0f} MW MAE {S.mean(map(abs, e)):.0f} MW".replace("endning", "ending"))


if __name__ == "__main__":
    main()
