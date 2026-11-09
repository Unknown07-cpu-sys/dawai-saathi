"""All time handling lives here so every module follows one rule:

    Store times in the database as UTC. Convert to Indian time only when showing them.

Indian Standard Time helpers will be added in Milestone 3, when reminders need them.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """The current time in UTC, without a timezone label.

    SQLite does not remember timezones, so we always store "naive" UTC times.
    Every *_at column in the database uses this function for its default value.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
