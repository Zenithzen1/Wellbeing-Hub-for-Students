"""The one place the app asks for the time.

Services call clock.now() instead of datetime.now() so tests can freeze or jump time
("fast-forward 24 hours and check the reminder fired"). Times are stored in UTC and
shown in Asia/Dubai time (UTC+4, no daylight saving).
"""

from datetime import datetime, timedelta, timezone

DUBAI = timezone(timedelta(hours=4), "Asia/Dubai")

_frozen: datetime | None = None


def now() -> datetime:
    """Current time, timezone-aware UTC (or the frozen time in tests)."""
    return _frozen if _frozen is not None else datetime.now(timezone.utc)


def to_local(dt: datetime) -> datetime:
    """A UTC datetime shown in Dubai time."""
    return dt.astimezone(DUBAI)


# --- test helpers -------------------------------------------------------------

def freeze(at: datetime) -> None:
    """Stop the clock at `at` (must be timezone-aware)."""
    global _frozen
    if at.tzinfo is None:
        raise ValueError("freeze() needs a timezone-aware datetime")
    _frozen = at.astimezone(timezone.utc)


def advance(delta: timedelta) -> None:
    """Move a frozen clock forward."""
    global _frozen
    if _frozen is None:
        raise RuntimeError("advance() only works on a frozen clock")
    _frozen += delta


def unfreeze() -> None:
    global _frozen
    _frozen = None
