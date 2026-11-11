"""All time handling lives here so every module follows one rule:

    Store times in the database as UTC. Convert to Indian time only when showing them.

Milestone 2 added the display helpers (to_ist, format_ist) for consent and verification times.
Helpers for scheduling reminders in Indian time will be added in Milestone 3.
"""

from datetime import datetime, timedelta, timezone

# India is UTC+05:30 all year round (no daylight saving), so a fixed offset is enough.
IST_OFFSET = timedelta(hours=5, minutes=30)


def utcnow() -> datetime:
    """The current time in UTC, without a timezone label.

    SQLite does not remember timezones, so we always store "naive" UTC times.
    Every *_at column in the database uses this function for its default value.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_ist(moment: datetime) -> datetime:
    """A stored (naive UTC) time as Indian Standard Time, for display only."""
    return moment + IST_OFFSET


def format_ist(moment: datetime | None) -> str:
    """For example "09 Nov 2026, 10:00 IST". An empty value gives an empty text."""
    if moment is None:
        return ""
    return to_ist(moment).strftime("%d %b %Y, %H:%M") + " IST"
