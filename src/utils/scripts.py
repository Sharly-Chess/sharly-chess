import argparse
import os


def init_script() -> list[str]:
    """Initialize a script by fixing the circular import and switching the path.
    It has to be used before any import from the project.
    If used with an argument parser, arguments have to be retrieved
    through this function."""

    # Has to be executed before plugin_manager to avoid initializing from the wrong path
    path_parser = argparse.ArgumentParser(add_help=False)
    path_parser.add_argument('--path', '-p', default='.')
    args, remaining_args = path_parser.parse_known_args()
    os.chdir(args.path)

    # Needs to be imported first to avoid circular import
    from plugins import manager  # Noqa E402

    return remaining_args
