import argparse
import ctypes
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')


def default_workdir() -> Path:
    """Determine the default working directory (where events, logs, etc. are stored)."""
    # Running as PyInstaller frozen?
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable).resolve()
        if sys.platform == 'darwin':
            # Case: macOS .app onedir
            # .../My.app/Contents/MacOS/exe
            if (
                exe.parent.name == 'MacOS'
                and exe.parent.parent.name == 'Contents'
                and exe.parent.parent.parent.suffix == '.app'
            ):
                return exe.parent.parent.parent.parent  # -> parent of the .app bundle
            # Case: onefile or frozen onedir (not .app)
            return exe.parent
        else:
            return exe.parent

    # Dev/unfrozen
    return Path.cwd()


def init_script() -> list[str]:
    """Initialize a script by fixing the circular import and switching the path.
    It has to be used before any import from the project.
    If used with an argument parser, arguments have to be retrieved
    through this function."""

    # Has to be executed before plugin_manager to avoid initializing from the wrong path
    path_parser = argparse.ArgumentParser(add_help=False)
    path_parser.add_argument('--path', '-p')
    args, remaining_args = path_parser.parse_known_args()
    if args.path:
        path = Path(args.path)
        os.environ['SC_MANUAL_PATH_USED'] = '1'
    else:
        path = default_workdir()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(str(path))
    load_dotenv()

    return remaining_args


def check_windows_defender_exception(arguments: list[str]):
    # Intended to be used while the program is already running, so has to run before any log import
    if sys.platform != 'win32':
        return arguments
    defender_parser = argparse.ArgumentParser(add_help=False)
    defender_parser.add_argument(
        '--win-defender-exception-path',
        type=str,
    )
    args, remaining_args = defender_parser.parse_known_args(arguments)
    def_path = args.win_defender_exception_path
    if not def_path:
        return remaining_args
    params = [
        '/C',
        'powershell',
        '-Command',
        f'"Add-MpPreference -ExclusionPath """{def_path}""" -Force"',
    ]
    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None, 'runas', 'cmd.exe', ' '.join(params), None, 0
    )
    sys.exit(0 if result > 32 else 1)
