"""Household local time — single source of truth for IST resolution.

The household is IST-based; the container's ambient timezone is UTC (Docker
default). occurred_on/"yesterday" resolution (expenses) and the scheduler's
Monday 10:00 AM fire semantics (reports) both key off this — anything that
needs "the household's today" imports from here rather than constructing its
own ZoneInfo("Asia/Kolkata").
"""

import datetime
from zoneinfo import ZoneInfo

HOUSEHOLD_TZ = ZoneInfo("Asia/Kolkata")


def now() -> datetime.datetime:
    return datetime.datetime.now(HOUSEHOLD_TZ)


def today() -> datetime.date:
    return now().date()
