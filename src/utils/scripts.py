import argparse
import os
from pathlib import Path
import sys


def default_workdir() -> Path:
    """Determine the default working directory."""
    # Running as PyInstaller frozen?
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable).resolve()
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
    # Dev/unfrozen
    return Path.cwd()


def init_script() -> list[str]:
    """Initialize a script by fixing the circular import and switching the path.
    It has to be used before any import from the project.
    If used with an argument parser, arguments have to be retrieved
    through this function."""

    # Has to be executed before plugin_manager to avoid initializing from the wrong path
    path_parser = argparse.ArgumentParser(add_help=False)
    path_parser.add_argument('--path', '-p', default=str(default_workdir()))
    args, remaining_args = path_parser.parse_known_args()
    os.chdir(args.path)

    # Needs to be imported first to avoid circular import
    from plugins import manager  # Noqa E402

    return remaining_args
