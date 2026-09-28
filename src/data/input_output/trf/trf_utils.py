import re
from contextlib import suppress
from datetime import date, datetime
from typing import overload


def float_display(value: float | None, width: int) -> str:
    if value is None:
        return ' ' * width
    return f'{value:.1f}'.rjust(width)


@overload
def int_or_default(string: str, default: int) -> int: ...


@overload
def int_or_default(string: str, default: None = None) -> int | None: ...


def int_or_default(string: str, default: int | None = None) -> int | None:
    if string == '' or string.isspace():
        return default
    return int(string)


def float_or_default(string: str, default: float | None = None) -> float | None:
    if string == '' or string.isspace():
        return default
    return float(string)


def _split_parts(value: str, width: int) -> list[str]:
    return [value[i : i + width].strip() for i in range(0, len(value.rstrip()), width)]


def split_ints(value: str, width: int) -> list[int]:
    return [int(part) for part in _split_parts(value, width)]


def split_optional_ints(value: str, width: int) -> list[int | None]:
    return [int(part or 0) or None for part in _split_parts(value, width)]


#: The date forms a 042 / 052 / birth-date field is read in. TRF26 asks
#: for ``YYYY/MM/DD`` on all three, and that is what we write; the rest
#: are forms found in files other programs produce, accepted so those
#: files load. ``%y/%m/%d`` is what the Gacrux tournament generator
#: writes, the two-digit year mapping to 1969-2068 as Python does it;
#: older files write the same year-first order with dots. Month names are resolved from the table below rather than through
#: ``%b``, which reads the process locale and so would parse an English
#: file only on an English-speaking machine.
TRF_DATE_READ_FORMATS = (
    '%Y/%m/%d',
    '%y/%m/%d',
    '%Y-%m-%d',
    '%Y.%m.%d',
    '%y.%m.%d',
    '%d.%m.%Y',
    '%d. %m. %Y',
    '%d/%m/%Y',
)

_ENGLISH_MONTHS = {
    month: index
    for index, month in enumerate(
        (
            'january',
            'february',
            'march',
            'april',
            'may',
            'june',
            'july',
            'august',
            'september',
            'october',
            'november',
            'december',
        ),
        start=1,
    )
}


def parse_trf_date(value: str) -> date | None:
    """The date a TRF field holds, or None when it holds none that can be
    read. A year alone (the ``YYYY/00/00`` a birth date may carry) is not
    a date and is not returned here."""
    value = value.strip()
    if not value:
        return None
    for date_format in TRF_DATE_READ_FORMATS:
        with suppress(ValueError):
            return datetime.strptime(value, date_format).date()
    return _parse_month_name_date(value)


def _parse_month_name_date(value: str) -> date | None:
    """``May 29, 2020`` and ``29 May 2020``, written by programs that put
    a month name where the format asks for digits."""
    parts = re.split(r'[\s,]+', value.lower())
    if len(parts) != 3:
        return None
    month: int | None = None
    numbers: list[int] = []
    for part in parts:
        for name, index in _ENGLISH_MONTHS.items():
            if part == name or (len(part) >= 3 and name.startswith(part)):
                month = index
                break
        else:
            if not part.isdigit():
                return None
            numbers.append(int(part))
    if month is None or len(numbers) != 2:
        return None
    day, year = sorted(numbers)
    with suppress(ValueError):
        return date(year, month, day)
    return None


def parse_trf_year(value: str) -> int | None:
    """The year a birth date holds when it names no day: TRF26 writes an
    unknown day and month as ``YYYY/00/00``, and older files often carry
    the bare year."""
    match = re.match(r'^(\d{4})(?:[/.-]00[/.-]00)?$', value.strip())
    return int(match.group(1)) if match else None
