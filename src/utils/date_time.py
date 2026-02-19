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
