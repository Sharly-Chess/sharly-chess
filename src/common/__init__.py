import importlib.metadata
import os
import plistlib
import re
import shutil
import subprocess
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
FLATPAK_ID = os.environ.get('FLATPAK_ID')
DEVEL_ENV: bool = not getattr(sys, 'frozen', False) and not FLATPAK_ID
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


def _app_base_dir() -> Path:
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

    # Other frozen (non-.app) onedir
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    # Dev: project / package root (where pyproject.toml is)
    return Path(__file__).resolve().parents[2]


DATA_DIR_ENV = 'SHARLY_CHESS_DEV_DATA_DIR' if DEVEL_ENV else 'SHARLY_CHESS_DATA_DIR'
PREVIOUS_DATA_DIR_ENV = DATA_DIR_ENV + '_PREVIOUS'


def app_data_dir() -> Path:
    if FLATPAK_ID:
        return Path()
    env_path = os.environ.get(DATA_DIR_ENV)
    if env_path:
        return Path(env_path)
    # macOS reads the chosen location from the plist (dev or built), so the
    # relocation works without depending on shell env vars.
    if sys.platform == 'darwin':
        return _macos_data_dir()
    if DEVEL_ENV:
        return BASE_DIR / 'dev-data'
    match sys.platform:
        case 'win32':
            return Path.home() / 'AppData' / 'Local' / 'Sharly Chess'
        case _:
            raise NotImplementedError(f'{sys.platform=}')


# macOS records the data location in a small plist at a fixed support directory,
# so the choice survives even when the data itself lives elsewhere. An env var
# cannot work here: a GUI .app launched from Finder never sources the shell
# profile, so an exported variable would simply be invisible to the app.
MACOS_SUPPORT_DIR = (
    Path.home() / 'Library' / 'Application Support' / 'com.sharlychess.thp'
)
# Lives next to (not inside) the data folder, so it survives the data moving.
MACOS_DATA_PLIST = MACOS_SUPPORT_DIR.parent / 'com.sharlychess.plist'


def _read_macos_data_plist() -> dict:
    try:
        with open(MACOS_DATA_PLIST, 'rb') as plist_file:
            return plistlib.load(plist_file)
    except (FileNotFoundError, OSError, plistlib.InvalidFileException):
        return {}


def _macos_data_dir() -> Path:
    custom = _read_macos_data_plist().get('data_directory')
    if custom:
        return Path(custom)
    if DEVEL_ENV:
        return BASE_DIR / 'dev-data'
    return MACOS_SUPPORT_DIR


BASE_DIR: Path = _app_base_dir()

# Architecture of the directory containing the app's data.
DATA_DIR = app_data_dir()
BACKUP_BASE_DIR = DATA_DIR / 'backup'  # Dev only
ARCHIVES_DIR = DATA_DIR / 'archives'
CUSTOM_DIR = DATA_DIR / 'custom'
CUSTOM_PLACE_CARDS_DIR = CUSTOM_DIR / 'place_cards'
DATA_SOURCES_DIR = DATA_DIR / 'data_sources'
VERSION_DATA_DIR = DATA_DIR / f'v{SHARLY_CHESS_VERSION}'
EVENTS_DIR = VERSION_DATA_DIR / 'events'
LOG_DIR = VERSION_DATA_DIR / 'logs'
TMP_DIR = VERSION_DATA_DIR / 'tmp'
CONFIG_FILE = VERSION_DATA_DIR / '.scc'
LOG_FILE = LOG_DIR / f'{APP_NAME}.log'

# Example paths (dev)
EXAMPLES_DIR = BASE_DIR / 'examples'
EXAMPLE_EVENTS_DIR = EXAMPLES_DIR / 'events'
EXAMPLE_PLACE_CARDS_DIR = EXAMPLES_DIR / 'place_cards'

# Embedded paths
WEB_TEMPLATES_DIR = BASE_DIR / 'src' / 'web'
EMBEDDED_PLACE_CARDS_DIR = WEB_TEMPLATES_DIR / 'admin' / 'print' / 'place_cards'


# On Flatpak, large downloads must land in TMP_DIR (within the sandbox's writable area)
# rather than the system /tmp (a small tmpfs). On other platforms, None lets tempfile
# use the OS default so behaviour is unchanged.
TEMPFILE_DIR: Path | None = TMP_DIR if FLATPAK_ID else None

DATA_DIR.mkdir(parents=True, exist_ok=True)
if not os.access(DATA_DIR, os.W_OK):
    raise SharlyChessException(f'Data path [{DATA_DIR.absolute()}] is not writable.')

IS_NEW_INSTALL = not VERSION_DATA_DIR.exists()


def set_env_variable(name: str, value: str):
    match sys.platform:
        case 'win32':
            subprocess.Popen(['setx', name, value], shell=True)
        case 'linux' | 'darwin':
            bashrc = Path.home() / '.bashrc'
            with open(bashrc, 'a') as f:
                f.write(f'\nexport {name}="{value}"\n')
    os.environ[name] = value


def _write_macos_data_plist(data: dict):
    MACOS_DATA_PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(MACOS_DATA_PLIST, 'wb') as plist_file:
        plistlib.dump(data, plist_file)


def persist_data_directory(new_path: Path, previous_path: Path):
    """Persist a user-chosen data directory and schedule the existing content to
    be moved into it on the next launch.

    On macOS this is recorded in a plist under Application Support (a
    Finder-launched app never sees shell env vars); elsewhere it falls back to
    the environment-variable mechanism.
    """
    if sys.platform == 'darwin':
        data = _read_macos_data_plist()
        data['data_directory'] = str(new_path)
        data['move_from'] = str(previous_path)
        _write_macos_data_plist(data)
    else:
        set_env_variable(DATA_DIR_ENV, str(new_path))
        set_env_variable(PREVIOUS_DATA_DIR_ENV, str(previous_path))


def _pending_data_move_source() -> Path | None:
    """The directory whose content should be migrated into DATA_DIR, if any."""
    if sys.platform == 'darwin':
        move_from = _read_macos_data_plist().get('move_from')
        return Path(move_from) if move_from else None
    previous = os.environ.get(PREVIOUS_DATA_DIR_ENV)
    return Path(previous) if previous else None


def _clear_pending_data_move():
    if sys.platform == 'darwin':
        data = _read_macos_data_plist()
        if data.pop('move_from', None) is not None:
            _write_macos_data_plist(data)
    else:
        set_env_variable(PREVIOUS_DATA_DIR_ENV, '')


if (previous_dir := _pending_data_move_source()) is not None:
    # The data dir changed: move the previous content over if the new dir is empty.
    if previous_dir.exists() and not any(DATA_DIR.iterdir()):
        for elem_path in previous_dir.glob('*'):
            shutil.move(elem_path, DATA_DIR)
        from common.logger import get_logger

        logger = get_logger()
        logger.info(
            'Data directory moved from "%s" to "%s"',
            previous_dir,
            DATA_DIR,
        )
        _clear_pending_data_move()

for directory in (
    ARCHIVES_DIR,
    CUSTOM_DIR,
    DATA_SOURCES_DIR,
    EVENTS_DIR,
    LOG_DIR,
    TMP_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

try:
    with open(LOG_FILE, 'a'):
        pass
except OSError as error:
    raise SharlyChessException(
        f'Log file [{LOG_FILE.absolute()}] could not be opened: {error}'
    )

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
