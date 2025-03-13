import os
import re
import sys
import time
from collections import namedtuple
from datetime import datetime
from functools import wraps
from logging import Logger
from pathlib import Path

import unicodedata
from packaging.version import Version

from common.logger import get_logger

APP_NAME: str = 'papi-web'

"""True when the program is running in a development environment, False if running as an EXE file."""
DEVEL_ENV: bool = not getattr(sys, 'frozen', False)

"""True when experimental features are enabled (relying on an environment variable), False otherwise."""
EXPERIMENTAL_FEATURES_ENV_VAR: str = 'PAPI_WEB_EXPERIMENTAL'
EXPERIMENTAL_FEATURES: bool = os.environ.get(
    EXPERIMENTAL_FEATURES_ENV_VAR, ''
).upper() in [
    'ON',
    'TRUE',
    '1',
]

PAPI_WEB_VERSION = Version("2.4.25")

RGB = namedtuple('RGB', ['red', 'green', 'blue'])


logger: Logger = get_logger()


""" The temporary directory. """
TMP_DIR: Path = Path('tmp')

try:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError as pe:
    logger.critical('Could not create directory [%s]: %s', TMP_DIR.absolute(), pe)
    sys.exit()


#The base directory, differs for developers. base_dir must be used when looking for application files
#(images, templates, ...) while user file should be search in the current directory.
BASE_DIR: Path = (
    Path(__file__).resolve().parents[2] if DEVEL_ENV else Path(sys._MEIPASS) # type: ignore
)


def check_rgb_str(color: str) -> str:
    """Checks if a string is in #rrggbb format
    returns it back if it is, raises ValueError otherwise."""
    rgb: RGB = hexa_to_rgb(color)
    if rgb:
        return rgb_to_hexa(rgb)
    raise ValueError(f'check_rgb_str(color={color})')


def hexa_to_rgb(color: str) -> RGB | None:
    """Converts a string from #rrggbb to RGB(red, green, blue) format."""
    hex_pattern = re.compile(
        '^#?(?P<R>[0-9a-f]{2})(?P<G>[0-9a-f]{2})(?P<B>[0-9a-f]{2})$'
    )
    if matches := hex_pattern.match(color.strip().lower()):
        return (
            int(matches.group('R'), 16),
            int(matches.group('G'), 16),
            int(matches.group('B'), 16),
        )
    return None


def rgb_to_hexa(rgb: RGB) -> str:
    """Converts a color in RGB(red, green, blue) format to #rrggbb format."""
    return '#' + ''.join(f'{max(0, min(255, i)):02X}' for i in rgb)


def format_timestamp_date_time(ts: float | None = None) -> str:
    """Formats the given timestamp (now if None) to YYYY-mm-dd HH:MM format."""
    return datetime.strftime(
        datetime.fromtimestamp(ts if ts is not None else time.time()), '%Y-%m-%d %H:%M'
    )


def format_timestamp_date(ts: float | None = None) -> str:
    """Formats the given timestamp (now if None) to YYYY-mm-dd format."""
    return datetime.strftime(
        datetime.fromtimestamp(ts if ts is not None else time.time()), '%Y-%m-%d'
    )


def format_timestamp_time(ts: float | None = None) -> str:
    """Formats the given timestamp (now if None) to HH:MM format."""
    return datetime.strftime(
        datetime.fromtimestamp(ts if ts is not None else time.time()), '%H:%M'
    )


def show_duration(func):
    """This decorator prints the duration of methods."""

    @wraps(func)
    def show_duration_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        # first item in the args, ie `args[0]` is `self`
        logger.warning(
            '%.4fs %s.%s(%s %s)',
            total_time,
            args[0].__class__.__name__,
            func.__name__,
            args[1:],
            kwargs
        )
        return result

    return show_duration_wrapper


def unicode_normalize(string: str) -> str:
    """Removes the accents of the string, cf https://www.unicode.org/reports/tr15/#Norm_Forms"""
    return ''.join(
        filter(
            lambda c: not unicodedata.combining(c),
            unicodedata.normalize('NFKD', string),
        )
    )
