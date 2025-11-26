import importlib.metadata
import os
import re
import sys
import time
from collections import namedtuple
from datetime import datetime, date
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from packaging.version import Version

from common.exception import SharlyChessException

APP_NAME: str = 'sharly-chess'
SHARLY_CHESS_VERSION: Version = Version(importlib.metadata.version(APP_NAME))

# True when the program is running in a development environment, False if running as an EXE file.
DEVEL_ENV: bool = not getattr(sys, 'frozen', False)
TEST_ENV: bool = os.getenv('TEST_ENV') == 'true' or Path(sys.argv[0]).stem == 'pytest'

# True when experimental features are enabled, False otherwise.
_EXPERIMENTAL_FEATURES_ENABLED: bool = False


def enable_experimental_features(enabled: bool):
    global _EXPERIMENTAL_FEATURES_ENABLED
    _EXPERIMENTAL_FEATURES_ENABLED = enabled


def experimental_features_enabled() -> bool:
    global _EXPERIMENTAL_FEATURES_ENABLED
    return _EXPERIMENTAL_FEATURES_ENABLED


REQUEST_TIMEOUT: int = 10

RGB = namedtuple('RGB', ['red', 'green', 'blue'])

EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


""" The temporary directory. """
TMP_DIR: Path = Path('tmp')


def app_base_dir() -> Path:
    """
    Return the directory that holds bundled resources for:
      - Dev:      repo/source tree
      - Onefile:  sys._MEIPASS
      - macOS .app onedir: .../My.app/Contents/Resources
      - Other frozen onedir: directory next to the executable
    """

    # PyInstaller onefile
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        return Path(meipass)

    # macOS .app onedir
    try:
        exe = Path(sys.argv[0]).resolve()
        # .../My.app/Contents/MacOS/<exe>
        contents = exe.parent.parent
        if contents.name == 'Contents' and contents.parent.suffix == '.app':
            resources = contents / 'Resources'
            if resources.is_dir():
                return resources
    except Exception:
        pass

    # Other frozen (non-.app) onedir
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    # Dev: project / package root (adjust levels to your layout)
    return Path(__file__).resolve().parents[2]


BASE_DIR: Path = app_base_dir()

"""The events folder name, used to recover events from previous releases."""
EVENTS_FOLDER: str = 'events'
""" The event directory. """
EVENTS_DIR: Path = Path(EVENTS_FOLDER)

LOG_DIR: Path = Path('logs')
LOG_FILE: Path = LOG_DIR / f'{APP_NAME}.log'


try:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a'):
        pass
except OSError as error:
    raise SharlyChessException(
        f'Log file [{LOG_FILE.absolute()}] could not be opened: {error}\n'
        f'Write permission is most likely missing from '
        f'[{LOG_FILE.parent.parent.absolute()}].\n'
        f'Check the permissions then try again.'
    )


for directory in (EVENTS_DIR, TMP_DIR):
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except PermissionError as error:
        from common.logger import get_logger

        message = f'Could not create directory [{directory.absolute()}]: {error}'
        get_logger().critical(message)
        raise SharlyChessException(message)


if DEVEL_ENV:
    import tomllib
    from contextlib import suppress

    with suppress(KeyError):
        with open(BASE_DIR / 'pyproject.toml', 'rb') as f:
            version = tomllib.load(f)['project']['version']
        if Version(version) != SHARLY_CHESS_VERSION:
            from common.logger import get_logger

            get_logger().critical(
                'Installed %s version %s does not match defined '
                'version %s. Run `pip install -e .` then run %s again.',
                APP_NAME,
                SHARLY_CHESS_VERSION,
                version,
                APP_NAME,
            )
            raise ValueError(f'{SHARLY_CHESS_VERSION=}, {version=}')


def check_rgb_str(color: str) -> str:
    """Checks if a string is in #rrggbb format
    returns it back if it is, raises ValueError otherwise."""
    rgb: RGB | None = hexa_to_rgb(color)
    if rgb:
        return rgb_to_hexa(rgb)
    raise ValueError(f'check_rgb_str(color={color})')


def hexa_to_rgb(color: str) -> RGB | None:
    """Converts a string from #rrggbb to RGB(red, green, blue) format."""
    hex_pattern = re.compile(
        '^#?(?P<R>[0-9a-f]{2})(?P<G>[0-9a-f]{2})(?P<B>[0-9a-f]{2})$'
    )
    if matches := hex_pattern.match(color.strip().lower()):
        return RGB(
            int(matches.group('R'), 16),
            int(matches.group('G'), 16),
            int(matches.group('B'), 16),
        )
    return None


def rgb_to_hexa(rgb: RGB) -> str:
    """Converts a color in RGB(red, green, blue) format to #rrggbb format."""
    return '#' + ''.join(f'{max(0, min(255, i)):02X}' for i in rgb)


def format_timestamp(ts: float | None = None, format_: str = '%Y-%m-%d %H:%M') -> str:
    """Formats a timestamp (now if None) to the given format."""
    return datetime.strftime(
        datetime.fromtimestamp(ts if ts is not None else time.time()), format_
    )


def is_valid_email(email: str) -> bool:
    return EMAIL_RE.match(email) is not None


def is_http_url(url: str) -> bool:
    try:
        r = urlparse(url)
        return r.scheme in {'http', 'https'} and bool(r.netloc)
    except ValueError:
        return False


def format_date(date_: date | None = None) -> str:
    return (date_ or date.today()).strftime('%Y-%m-%d')


def format_date_range(start_date: date, stop_date: date | None = None) -> str:
    if not stop_date or start_date == stop_date:
        return format_date(start_date)
    return f'{format_date(start_date)} / {format_date(stop_date)}'


def get_date_timestamp(date_: date) -> float:
    return datetime.combine(date_, datetime.min.time()).timestamp()


def format_timestamp_date_time(ts: float | None = None) -> str:
    """Formats the given timestamp (now if None) to YYYY-mm-dd HH:MM format."""
    return format_timestamp(ts)


def format_timestamp_date(ts: float | None = None) -> str:
    """Formats the given timestamp (now if None) to YYYY-mm-dd format."""
    return format_timestamp(ts, '%Y-%m-%d')


def format_timestamp_time(ts: float | None = None) -> str:
    """Formats the given timestamp (now if None) to HH:MM format."""
    return format_timestamp(ts, '%H:%M')


def show_duration(func):
    """This decorator prints the duration of methods."""

    @wraps(func)
    def show_duration_wrapper(*args, **kwargs):
        from common.logger import get_logger

        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        # first item in the args, ie `args[0]` is `self`
        get_logger().warning(
            '%.4fs %s.%s(%s %s)',
            total_time,
            args[0].__class__.__name__,
            func.__name__,
            args[1:],
            kwargs,
        )
        return result

    return show_duration_wrapper
