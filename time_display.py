"""Format stored UTC wall-clock times for UTC+8 display (ADR-0003)."""

from datetime import datetime, timedelta, timezone

_UTC8 = timezone(timedelta(hours=8))


def format_wall_clock_utc8(utc_dt: datetime, fmt: str) -> str:
    """Format a naive UTC datetime as UTC+8 with no timezone label."""
    aware_utc = utc_dt.replace(tzinfo=timezone.utc)
    return aware_utc.astimezone(_UTC8).strftime(fmt)
