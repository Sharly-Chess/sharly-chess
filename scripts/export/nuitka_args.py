"""Emit Nuitka argument list, mirroring the PyInstaller builder's collection.

Reuses the exact sources that project_builder._build_exe walks (plugin manager,
migration modules, installation checker, template/static/locale globs, credentials,
toga data) so the Nuitka bundle stays in parity with the PyInstaller one. Prints one
argument per line on stdout.

Run from the repo root with the venv python:
    ./venv/bin/python scripts/export/nuitka_args.py
"""

import os
import sys
from pathlib import Path
from pkgutil import iter_modules
from types import ModuleType

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / 'src'
sys.path.insert(0, str(SRC_DIR))
os.chdir(BASE_DIR)

import plugins.chess_results  # noqa: E402
import plugins.ffe  # noqa: E402
import plugins.fra_schools  # noqa: E402
from common.installation_checker import InstallationChecker  # noqa: E402
from database.sqlite.config import migrations as config_migrations  # noqa: E402
from database.sqlite.event import migrations as event_migrations  # noqa: E402
from plugins.manager import plugin_manager  # noqa: E402

VENV = Path(os.environ['VIRTUAL_ENV'])
if sys.platform == 'win32':
    VENV_LIB = VENV / 'Lib' / 'site-packages'
else:
    VENV_LIB = VENV / 'lib' / 'python3.13' / 'site-packages'

args: list[str] = []


def add(arg: str) -> None:
    args.append(arg)


# --- local packages (PyInstaller --hiddenimport that are whole trees) ---
for pkg in (
    'common',
    'data',
    'database',
    'plugins',
    'web',
    'gui',
    'utils',
    'antivirus',
):
    add(f'--include-package={pkg}')

# --- third-party modules pulled in dynamically ---
# These mirror the PyInstaller --hiddenimport list. The pyexcel_io.readers/database
# and jinja2.ext entries are extra: PyInstaller's bytecode scan finds them implicitly,
# Nuitka's static analysis needs them named.
for mod in (
    'babel.numbers',
    'pyexcel_io.writers',
    'pyexcel_io.readers',
    'pyexcel_io.database',
    'colorlog',
    'jinja2.ext',
):
    add(f'--include-module={mod}')

# toga loads widget/backend submodules lazily (toga.__getattr__ -> import_module);
# uvicorn resolves its loop/http/websocket/lifespan implementations by string via
# importlib. Both need their whole trees forced in, not just the top package.
framework_packages = ['toga', 'uvicorn', 'litestar']
if sys.platform == 'win32':
    framework_packages.append('toga_winforms')
elif sys.platform == 'darwin':
    framework_packages += ['toga_cocoa', 'rubicon']
else:
    framework_packages.append('toga_gtk')
for pkg in framework_packages:
    add(f'--include-package={pkg}')

backend_pkg = {'win32': 'toga_winforms', 'darwin': 'toga_cocoa'}.get(
    sys.platform, 'toga_gtk'
)
for pkg in ('toga', backend_pkg, 'iso4217parse', 'database', 'plugins'):
    add(f'--include-package-data={pkg}')

add('--include-distribution-metadata=sharly-chess')

# --- migration submodules (iter_modules, same as the PyInstaller builder) ---
migration_base_modules: list[ModuleType] = [
    config_migrations,
    event_migrations,
] + [
    plugin.base_migration_module
    for plugin in plugin_manager.all_plugins
    if plugin.base_migration_module
]
for base_module in migration_base_modules:
    for _, module, _ in iter_modules(base_module.__path__):
        add(f'--include-module={base_module.__name__}.{module}')

# --- data files (identical walk to _build_exe) ---
files: list[Path] = []
web_dir = SRC_DIR / 'web'
files += [f for f in (web_dir / 'templates').glob('**/*') if f.is_file()]
for templates_path in plugin_manager.templates_paths:
    files += [f for f in templates_path.glob('**/*') if f.is_file()]
for locale_path in plugin_manager.locale_paths:
    files += [f for f in locale_path.glob('**/*.mo') if f.is_file()]
for static_path in plugin_manager.static_paths:
    files += [f for f in static_path.glob('**/*') if f.is_file()]
static_dir = web_dir / 'static'
for sub in ('fonts', 'images', 'css', 'js'):
    files += [f for f in (static_dir / sub).glob('**/*') if f.is_file()]
for installer in InstallationChecker.web_lib_installers:
    files += [
        installer.version_install_dir / lib_file for lib_file in installer.lib_files
    ]
lib_dir = static_dir / 'lib'
files += [
    lib_dir / 'htmx' / 'sortable.js',
    lib_dir / 'htmx' / 'morphdom-swap.js',
    lib_dir / 'polyglot' / 'polyglot.js',
    lib_dir / 'select2' / 'themes' / 'dark-bootstrap-5.css',
]
custom_dir = SRC_DIR / 'custom'
files += [f for f in custom_dir.glob('**/*') if f.is_file()]
files += [f for f in (BASE_DIR / 'locale').glob('**/*.mo') if f.is_file()]
for executable_installer in InstallationChecker.executable_installers:
    installer_dir = executable_installer.executable_dir
    if installer_dir.exists():
        files += [f for f in installer_dir.glob('**/*') if f.is_file()]
files += [
    SRC_DIR / '.fide-database-enc-credentials',
    plugins.chess_results.PLUGIN_DIR / '.credentials',
    plugins.ffe.PLUGIN_DIR / '.sql-server-credentials',
    plugins.ffe.PLUGIN_DIR / '.database-enc-credentials',
    plugins.fra_schools.PLUGIN_DIR / '.database-enc-credentials',
]
gui_dir = SRC_DIR / 'gui'
files += [f for f in gui_dir.glob('**/*') if f.is_file() and f.suffix != '.py']

# Map each file to a Nuitka --include-data-files=SRC=DEST (DEST keeps the
# BASE_DIR-relative layout the app expects at runtime).
for file in files:
    if not file.is_file():
        continue
    try:
        dest = file.relative_to(BASE_DIR)
    except ValueError:
        dest = Path(file.name)
    add(f'--include-data-files={file}={dest}')

# pyproject.toml is read at startup for the version.
add(f'--include-data-files={BASE_DIR / "pyproject.toml"}=pyproject.toml')

# toga / iso4217parse loose data files (venv-relative, like the PyInstaller builder).
for file in [
    VENV_LIB / 'toga' / '__init__.pyi',
    VENV_LIB / 'iso4217parse' / 'data.json',
    VENV_LIB / 'iso4217parse' / 'symbols.json',
]:
    if file.is_file():
        rel = file.relative_to(VENV_LIB)
        add(f'--include-data-files={file}={rel}')

print('\n'.join(args))
