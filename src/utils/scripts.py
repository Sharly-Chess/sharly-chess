import argparse
import os
from pathlib import Path
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')


def default_workdir() -> Path:
    """Determine the default working directory (where events, logs, etc. are stored)."""
    import os

    # Running as PyInstaller frozen?
    if getattr(sys, 'frozen', False):
        # Case: Linux AppImage - return directory containing the AppImage file
        appdir = os.environ.get('APPDIR')
        if appdir:
            # AppImage sets APPDIR to the mount point
            # We want the directory where the AppImage file is located (with events, logs, etc.)
            # The AppRun script changes to this directory, so use current working directory
            current = Path.cwd()

            # Check if current directory has user folders (events, logs, etc.)
            # This is the most reliable indicator since AppRun changes to this directory
            if (current / 'events').exists() or (current / 'logs').exists():
                return current

            # Try ARGV0 to get the AppImage file location
            argv0 = os.environ.get('ARGV0')
            if argv0:
                argv0_path = Path(argv0)
                # If ARGV0 is the AppImage file itself, get its parent
                if argv0_path.exists() and argv0_path.suffix == '.AppImage':
                    appimage_dir = argv0_path.resolve().parent
                    if appimage_dir.exists():
                        return appimage_dir
                # If ARGV0 is a script, try to find the AppImage in the same directory
                elif argv0_path.exists():
                    appimage_dir = argv0_path.resolve().parent
                    # Look for AppImage file in this directory
                    for appimage_file in appimage_dir.glob('*.AppImage'):
                        return appimage_dir

            # Fallback: check parent of current directory
            if (current.parent / 'events').exists() or (
                current.parent / 'logs'
            ).exists():
                return current.parent

            # Last fallback: return current working directory
            # (AppRun script should have set this to the AppImage directory)
            return current

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

    return remaining_args
