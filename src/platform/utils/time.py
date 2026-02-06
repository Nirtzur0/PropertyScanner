from __future__ import annotations

from datetime import datetime, timezone
import time


def utcnow() -> datetime:
    """
    Return a naive datetime representing the current UTC time.

    This avoids deprecated `datetime.utcnow()` while keeping naive datetimes,
    which is what the current SQLite + pandas plumbing expects throughout
    the codebase.
    """

    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcfromtimestamp(ts: float) -> datetime:
    """
    Return a naive datetime representing a UTC timestamp.

    Prefer this over deprecated `datetime.utcfromtimestamp()`.
    """

    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def unix_ts() -> int:
    """Seconds since epoch (UTC). Safe for ID suffixes and cache keys."""

    return int(time.time())

