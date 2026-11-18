"""UTC helpers: the database stores UTC, the UI renders Europe/Rome."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC.

    SQLite returns naive datetimes even for ``DateTime(timezone=True)`` columns;
    values are always written in UTC, so a naive value is interpreted as UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_timezone(value: datetime, tz_name: str) -> datetime:
    """Convert a stored datetime to the display timezone."""
    return ensure_utc(value).astimezone(ZoneInfo(tz_name))


def isoformat_utc(value: datetime) -> str:
    """Render a datetime as an ISO 8601 UTC string with a ``Z`` suffix."""
    return ensure_utc(value).isoformat().replace("+00:00", "Z")
