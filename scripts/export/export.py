import argparse
import sys
from pathlib import Path

from logging import Logger
from packaging.version import Version, InvalidVersion

sys.path.extend(
    map(
        str,
        [
            Path(__file__).parents[2],  # The root path
            Path(__file__).parents[2]
            / 'src',  # The path to the sources of the application
            Path(__file__).parents[2]
            / 'scripts/export',  # The path to the scripts of the application
        ],
    )
)

from common.i18n import update_i18n_files

from common import enable_experimental_features

from common import SHARLY_CHESS_VERSION
from common.logger import get_logger
from common.installation_checker import (
    InstallationChecker,
)

from .project_builder import ProjectBuilder
from .linux.linux_project_builder import LinuxProjectBuilder
from .macos.mac_project_builder import MacProjectBuilder
from .windows.win_project_builder import WinProjectBuilder

# Enable experimental features to force the installation of the experimental tools and libs before exporting
enable_experimental_features(True)

logger: Logger = get_logger()


def get_project_builder() -> ProjectBuilder:
    """Return the project of the current platform"""
    # use sys.platform to distinguish Mac and Linux (os.name returns 'posix' for both)
    match sys.platform:
        case 'win32':
            return WinProjectBuilder()
        case 'darwin':
            return MacProjectBuilder()
        case 'linux':
            return LinuxProjectBuilder()
        case _:
            raise RuntimeError('No project builder for ')


def main():
    # option --github is used when generating the EXE file from a GITHUB action
    # to verify that the name of the tag matches the Sharly Chess version.
    # option --preserve-build is used to skip cleanup for signing purposes
    parser = argparse.ArgumentParser()
    parser.add_argument('--github', type=str)
    args = parser.parse_args()
    if args.github:
        if SHARLY_CHESS_VERSION != Version(args.github):
            raise InvalidVersion(
                f'Version [{args.github}] does not match (expected [{SHARLY_CHESS_VERSION}]).'
            )
        else:
            logger.info('Version [%s] is valid.', args.github)
    else:
        logger.info('The version is not verified (not running on GitHub).')
    if not InstallationChecker.check():
        sys.exit(1)
    if not update_i18n_files(generate_doc=False):
        logger.error('You must update the translations.')
        sys.exit(1)
    if not get_project_builder().run():
        logger.error('Export failed.')
        sys.exit(1)


if __name__ == '__main__':
    main()
