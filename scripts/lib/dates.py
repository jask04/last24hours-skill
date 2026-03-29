"""Date utilities for last24hours skill."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


def get_date_range(days: int = 1) -> Tuple[str, str]:
    """Get the date range for the last N days.

    Returns:
        Tuple of (from_date, to_date) as YYYY-MM-DD strings
    """
    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=days)
    return from_date.isoformat(), today.isoformat()


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string in various formats.

    Supports: YYYY-MM-DD, ISO 8601, Unix timestamp
    """
    if not date_str:
        return None

    # Try Unix timestamp (from Reddit)
    try:
        ts = float(date_str)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass

    # Try ISO formats
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def timestamp_to_date(ts: Optional[float]) -> Optional[str]:
    """Convert Unix timestamp to YYYY-MM-DD string."""
    if ts is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.date().isoformat()
    except (ValueError, TypeError, OSError):
        return None


def get_date_confidence(date_str: Optional[str], from_date: str, to_date: str) -> str:
    """Determine confidence level for a date.

    Args:
        date_str: The date to check (YYYY-MM-DD or None)
        from_date: Start of valid range (YYYY-MM-DD)
        to_date: End of valid range (YYYY-MM-DD)

    Returns:
        'high', 'med', or 'low'
    """
    if not date_str:
        return 'low'

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        start = datetime.strptime(from_date, "%Y-%m-%d").date()
        end = datetime.strptime(to_date, "%Y-%m-%d").date()

        if start <= dt <= end:
            return 'high'
        elif dt < start:
            # Older than range
            return 'low'
        else:
            # Future date (suspicious)
            return 'low'
    except ValueError:
        return 'low'


def days_ago(date_str: Optional[str]) -> Optional[int]:
    """Calculate how many days ago a date is.

    Returns None if date is invalid or missing.
    """
    if not date_str:
        return None

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        delta = today - dt
        return delta.days
    except ValueError:
        return None


def recency_score(date_str: Optional[str], max_days: int = 2) -> int:
    """Calculate recency score (0-100) based on days.

    0 days ago = 100, max_days ago = 0, clamped.
    """
    age = days_ago(date_str)
    if age is None:
        return 0  # Unknown date gets worst score

    if age < 0:
        return 100  # Future date (treat as today)
    if age >= max_days:
        return 0

    return int(100 * (1 - age / max_days))


def hours_ago(date_str: Optional[str]) -> Optional[float]:
    """Calculate how many hours ago a date/datetime is.

    Tries to parse as a full datetime first (for hour-level precision),
    then falls back to date-only parsing.
    Returns None if date is invalid or missing.
    """
    if not date_str:
        return None

    parsed = parse_date(date_str)
    if parsed is not None:
        now = datetime.now(timezone.utc)
        delta = now - parsed
        return delta.total_seconds() / 3600

    return None


def recency_score_hours(date_str: Optional[str], max_hours: int = 48) -> int:
    """Calculate recency score (0-100) based on hours.

    0 hours ago = 100, max_hours ago = 0, with linear decay.
    Items under 6 hours old get a bonus bump to at least 90.
    """
    age = hours_ago(date_str)
    if age is None:
        return 0  # Unknown date gets worst score

    if age < 0:
        return 100  # Future date (treat as now)
    if age >= max_hours:
        return 0

    # Linear decay over max_hours
    base = int(100 * (1 - age / max_hours))

    # Bonus: items under 6 hours get pushed toward 100
    if age <= 6:
        base = max(base, 90)

    return base
