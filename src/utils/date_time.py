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


def format_date(date_: date | None = None, compact_no_year: bool = True) -> str:
    formatter = _date_formatter()
    today = date.today()
    if not date_:
        date_ = today
    return date_.strftime(
        formatter.python_format_no_year
        if compact_no_year and date_.year == today.year
        else formatter.python_format
    )


def format_datetime(datetime_: datetime, compact_no_year: bool = True) -> str:
    formatter = _date_formatter()
    return datetime_.strftime(
        formatter.datetime_python_format_no_year
        if compact_no_year and datetime_.year == date.today().year
        else formatter.datetime_python_format
    )


def format_iso_date(iso_date: str, compact_no_year: bool = True) -> str:
    return format_date(date.fromisoformat(iso_date), compact_no_year)


def format_time(datetime_: datetime) -> str:
    return datetime_.strftime(_date_formatter().time_python_format)


def format_date_range(
    start_date: date, stop_date: date | None = None, compact_no_year: bool = True
) -> str:
    if not stop_date or start_date == stop_date:
        return format_date(start_date, compact_no_year)
    return _date_formatter().range_separator.join(
        [
            format_date(start_date, compact_no_year),
            format_date(stop_date, compact_no_year),
        ]
    )


def get_date_timestamp(date_: date) -> float:
    return datetime.combine(date_, datetime.min.time()).timestamp()
