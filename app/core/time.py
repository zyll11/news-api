from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Treat naive datetimes (e.g. returned by SQLite) as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
