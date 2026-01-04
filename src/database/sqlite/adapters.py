import sqlite3
from datetime import date, datetime


def adapt_date_iso(val: date) -> str:
    """Adapt datetime.date to ISO 8601 date."""
    return val.isoformat()


def adapt_datetime_iso(val: datetime) -> str:
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat(' ')


def convert_date(val: bytes) -> date:
    """Convert ISO 8601 date to datetime.date object."""
    return date.fromisoformat(val.decode('utf-8'))


def convert_datetime(val: bytes) -> datetime:
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.fromisoformat(val.decode('utf-8'))


def register_adapters() -> None:
    """Register SQLite adapters and converters for date and datetime."""
    sqlite3.register_adapter(date, adapt_date_iso)
    sqlite3.register_adapter(datetime, adapt_datetime_iso)
    sqlite3.register_converter('date', convert_date)
    sqlite3.register_converter('timestamp', convert_datetime)
