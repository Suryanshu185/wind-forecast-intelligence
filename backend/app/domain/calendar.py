"""Calendar and decision-cutoff logic (methodology §1). Pure functions over stdlib `zoneinfo`.

Conventions
* Delivery date = Europe/London settlement date.
* A settlement period (SP) is identified by its UTC start; SPs are 30 minutes long.
* Expected SPs for a date are *calculated from the calendar* (48, or 46/50 on clock-change days),
  never inferred from data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LONDON = ZoneInfo("Europe/London")
SP = timedelta(minutes=30)
HOUR = timedelta(hours=1)


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError(f"unknown IANA time zone {name!r}") from exc


def london_date(instant_utc: datetime) -> date:
    """The Europe/London calendar date containing a UTC instant."""
    _require_aware(instant_utc)
    return instant_utc.astimezone(LONDON).date()


def local_midnight_utc(d: date, tz: ZoneInfo = LONDON) -> datetime:
    """UTC instant of local midnight at the start of `d`.

    Midnight does not fall inside a DST gap in Europe/London (transitions occur at 01:00/02:00 local),
    so this is unambiguous for the delivery calendar.
    """
    return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)


def floor_hour(instant_utc: datetime) -> datetime:
    _require_aware(instant_utc)
    return instant_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def expected_sp_starts(d: date) -> list[datetime]:
    """All SP start instants (UTC) in London date `d`: 48 normally, 46 or 50 on clock-change days."""
    start, end = local_midnight_utc(d), local_midnight_utc(d + timedelta(days=1))
    out: list[datetime] = []
    t = start
    while t < end:
        out.append(t)
        t += SP
    return out


def expected_sp_starts_range(first: date, last: date) -> list[datetime]:
    if last < first:
        raise ValueError("last date precedes first date")
    out: list[datetime] = []
    d = first
    while d <= last:
        out.extend(expected_sp_starts(d))
        d += timedelta(days=1)
    return out


def cutoff_instant(
    delivery_date: date,
    cutoff_time: time,
    days_before: int = 1,
    cutoff_tz: ZoneInfo = LONDON,
) -> datetime:
    """UTC instant of the purchasing-decision cutoff for a delivery date.

    decision date = delivery date - days_before (a calendar date); the clock time is read in `cutoff_tz`.
    DST edge cases follow `zoneinfo` fold=0 semantics, which is the documented rule:
    * non-existent local time (spring-forward gap) -> interpreted with the pre-transition offset, i.e. it
      lands the same distance after the gap start (01:30 on a 01:00->02:00 gap = 02:30 local);
    * ambiguous local time (autumn overlap) -> the FIRST occurrence.
    """
    if days_before < 0:
        raise ValueError("days_before must be >= 0")
    decision_date = delivery_date - timedelta(days=days_before)
    naive_clock = time(cutoff_time.hour, cutoff_time.minute, cutoff_time.second)
    local = datetime.combine(decision_date, naive_clock, tzinfo=cutoff_tz).replace(fold=0)
    return local.astimezone(UTC)


def _require_aware(dt: datetime) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive datetime is not allowed")
