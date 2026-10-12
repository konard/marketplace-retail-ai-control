"""Business days for deadlines and lead times."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

SATURDAY = 5


def is_business_day(day: date, holidays: Iterable[date] = ()) -> bool:
    """Monday to Friday, except holidays."""
    return day.weekday() < SATURDAY and day not in set(holidays)


def add_business_days(start: date, count: int, holidays: Iterable[date] = ()) -> date:
    """Return the day ``count`` business days after ``start``."""
    off = set(holidays)
    day = start
    while count > 0:
        day += timedelta(days=1)
        if is_business_day(day, off):
            count -= 1
    return day


def business_days_between(start: date, end: date, holidays: Iterable[date] = ()) -> int:
    """Count business days after ``start`` up to and including ``end``."""
    off = set(holidays)
    return sum(
        1
        for n in range(1, (end - start).days + 1)
        if is_business_day(start + timedelta(days=n), off)
    )
