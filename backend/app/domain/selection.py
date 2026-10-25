"""Point-in-time forecast-vintage selection (methodology §3). THE critical algorithm.

For a forecast hour interval, consider only vintages whose `publishTime` is at or before the decision
cutoff (minus an optional availability lag), and which pre-date the hour they describe; choose the latest.
`startTime` selects the target; it is never compared with the cutoff.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.models import Conflict, ForecastRecord

ConflictPolicy = Literal["exclude", "strict"]
UnavailableReason = Literal["no_eligible_forecast", "conflict"]


@dataclass(frozen=True, slots=True)
class Selection:
    """Outcome of selecting a forecast for one hourly interval."""

    row_stamp: datetime  # startTime of the WINDFOR row consulted
    hour_start: datetime  # start of the hour interval being described
    cutoff_utc: datetime  # effective cutoff (cutoff - availability lag)
    forecast_mw: float | None
    published_at: datetime | None
    lead_time_h: float | None  # hour_start - published_at, in hours
    reason: UnavailableReason | None  # set iff forecast_mw is None
    vintages_total: int  # all clean vintages targeting row_stamp (any publish time)
    vintages_eligible: int
    vintages_after_cutoff: int
    conflict_fallback: (
        bool  # latest eligible vintage was conflicted; an earlier one was used (exclude)
    )
    conflict_involved: bool  # a conflicted record was eligible for this interval

    @property
    def available(self) -> bool:
        return self.forecast_mw is not None


class ForecastIndex:
    """Forecast vintages indexed by target `startTime`, sorted by publish time."""

    def __init__(
        self, records: list[ForecastRecord], conflicts: list[Conflict] | None = None
    ) -> None:
        by_stamp: dict[datetime, list[ForecastRecord]] = defaultdict(list)
        for r in records:
            by_stamp[r.start_utc].append(r)
        self._clean: dict[datetime, list[ForecastRecord]] = {
            k: sorted(v, key=lambda r: r.publish_utc) for k, v in by_stamp.items()
        }
        self._publish_keys: dict[datetime, list[datetime]] = {
            k: [r.publish_utc for r in v] for k, v in self._clean.items()
        }
        conflicted: dict[datetime, list[datetime]] = defaultdict(list)
        for c in conflicts or []:
            if c.dataset == "WINDFOR" and c.publish_utc is not None:
                conflicted[c.start_utc].append(c.publish_utc)
        self._conflicted = {k: sorted(v) for k, v in conflicted.items()}

    def vintages(self, row_stamp: datetime) -> list[ForecastRecord]:
        """All clean vintages for a target row, ascending by publish time."""
        return list(self._clean.get(row_stamp, []))

    def conflicted_publish_times(self, row_stamp: datetime) -> list[datetime]:
        return list(self._conflicted.get(row_stamp, []))

    def select(
        self,
        row_stamp: datetime,
        hour_start: datetime,
        cutoff_utc: datetime,
        policy: ConflictPolicy = "exclude",
    ) -> Selection:
        clean = self._clean.get(row_stamp, [])
        pubs = self._publish_keys.get(row_stamp, [])
        # Eligible = published <= cutoff AND strictly before the hour described AND has a value.
        n_cutoff = bisect_right(pubs, cutoff_utc)
        eligible = [r for r in clean[:n_cutoff] if r.publish_utc < hour_start and r.mw is not None]
        conflicted = [
            p for p in self._conflicted.get(row_stamp, []) if p <= cutoff_utc and p < hour_start
        ]
        after_cutoff = len(clean) - n_cutoff

        best = eligible[-1] if eligible else None  # latest eligible: list is sorted ascending
        latest_conflict = conflicted[-1] if conflicted else None
        conflict_newer = latest_conflict is not None and (
            best is None or latest_conflict > best.publish_utc
        )

        def unavailable(reason: UnavailableReason) -> Selection:
            return Selection(
                row_stamp, hour_start, cutoff_utc, None, None, None, reason,
                len(clean), len(eligible), after_cutoff, False, bool(conflicted),
            )  # fmt: skip

        if policy == "strict" and conflict_newer:
            return unavailable("conflict")
        if best is None:
            return unavailable("conflict" if conflicted else "no_eligible_forecast")
        lead = (hour_start - best.publish_utc).total_seconds() / 3600.0
        return Selection(
            row_stamp, hour_start, cutoff_utc, best.mw, best.publish_utc, lead, None,
            len(clean), len(eligible), after_cutoff, conflict_newer, bool(conflicted),
        )  # fmt: skip
