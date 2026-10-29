from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Return UTC in the timezone-naive form stored by the current schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
