import importlib.metadata
import os
import re
import sys
from collections import namedtuple
from pathlib import Path
from urllib.parse import urlparse
from packaging.version import Version

from common.exception import SharlyChessException

APP_NAME: str = 'sharly-chess'
SHARLY_CHESS_VERSION: Version = Version(importlib.metadata.version(APP_NAME))

# True when the program is running in a development environment, False if running as an EXE file.
# We also consider Flatpak as a non-development environment.
DEVEL_ENV: bool = not getattr(sys, 'frozen', False) and not os.environ.get('FLATPAK_ID')
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
    Return the directory that holds bundled resources (project root with pyproject.toml):
      - Dev:      repo/source tree (where pyproject.toml is)
      - Onefile:  sys._MEIPASS
      - macOS .app onedir: .../My.app/Contents/Resources
      - Linux AppImage: AppDir/usr/share (bundled resources)
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

    # Linux AppImage - return AppDir/usr/share (bundled resources)
    if getattr(sys, 'frozen', False):
        try:
            # Check if we're running from AppImage (APPDIR is set by AppImage runtime)
            appdir = os.environ.get('APPDIR')
            if appdir:
                # AppImage sets APPDIR to the mount point
                # Bundled resources are in usr/share
                usr_share = Path(appdir) / 'usr' / 'share'
                if usr_share.exists():
                    return usr_share
                # Fallback to APPDIR itself
                return Path(appdir)
        except Exception:
            pass

    # Other frozen (non-.app) onedir
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    # Dev: project / package root (where pyproject.toml is)
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


def is_valid_email(email: str) -> bool:
    return EMAIL_RE.match(email) is not None


def is_http_url(url: str) -> bool:
    try:
        r = urlparse(url)
        return r.scheme in {'http', 'https'} and bool(r.netloc)
    except ValueError:
        return False
