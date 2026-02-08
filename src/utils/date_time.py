import time
from datetime import datetime, date

from utils.date_formatter import (
    DateFormatter,
    ISODateFormatter,
    EUDateFormatter,
    USDateFormatter,
)
from utils.entity import EntityManager


class DateFormatterManager(EntityManager[DateFormatter]):
    def entity_types(self) -> list[type[DateFormatter]]:
        return [
            ISODateFormatter,
            EUDateFormatter,
            USDateFormatter,
        ]


def _date_formatter() -> DateFormatter:
    from common.sharly_chess_config import SharlyChessConfig

    return SharlyChessConfig().date_formatter


def format_timestamp(ts: float | None, format_: str) -> str:
    """Formats a timestamp (now if None) to the given format."""
    return datetime.strftime(datetime.fromtimestamp(ts or time.time()), format_)


def format_timestamp_date_time(ts: float | None = None) -> str:
    return format_timestamp(ts, _date_formatter().datetime_python_format)


def format_timestamp_date(ts: float | None = None) -> str:
    return format_timestamp(ts, _date_formatter().python_format)


def format_date(date_: date | None = None) -> str:
    return (date_ or date.today()).strftime(_date_formatter().python_format)


def format_datetime(datetime_: datetime) -> str:
    return datetime_.strftime(_date_formatter().datetime_python_format)


def format_time(datetime_: datetime) -> str:
    return datetime_.strftime(_date_formatter().time_python_format)


def format_date_range(start_date: date, stop_date: date | None = None) -> str:
    if not stop_date or start_date == stop_date:
        return format_date(start_date)
    return _date_formatter().range_separator.join(
        [format_date(start_date), format_date(stop_date)]
    )


def get_date_timestamp(date_: date) -> float:
    return datetime.combine(date_, datetime.min.time()).timestamp()


def timestamp_to_datetime(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts) if ts is not None else None


def datetime_to_timestamp(dt: datetime | None) -> float | None:
    return dt.timestamp() if dt is not None else None


def timestamp_to_date(ts: float | None) -> date | None:
    return datetime.fromtimestamp(ts).date() if ts is not None else None


def date_to_timestamp(d: date | None) -> float | None:
    return get_date_timestamp(d) if d is not None else None
