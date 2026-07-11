import sys
from pathlib import Path

from logging import Logger

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

from common.i18n import update_i18n_files  # noqa: E402

from common import enable_experimental_features  # noqa: E402

from common.logger import get_logger  # noqa: E402
from common.installation_checker import (  # noqa: E402
    InstallationChecker,
)

from project_builder import ProjectBuilder  # type: ignore  # noqa: E402
from macos.mac_project_builder import MacProjectBuilder  # type: ignore  # noqa: E402
from windows.win_project_builder import WinProjectBuilder  # type: ignore  # noqa: E402

# Enable experimental features to force the installation of the experimental tools and libs before exporting
enable_experimental_features(True)

logger: Logger = get_logger()


def get_project_builder() -> ProjectBuilder:
    """Return the project of the current platform"""
    # use platform.system to distinguish Mac and Linux (os.name returns 'posix' for both)
    match sys.platform:
        case 'win32':
            return WinProjectBuilder()
        case 'darwin':
            return MacProjectBuilder()
        case 'linux':
            raise RuntimeError(
                'Linux builds use Flatpak. Run flatpak-builder with the manifest at scripts/export/linux/flatpak/configuration/.'
            )
        case _:
            raise RuntimeError(f'No project builder for platform [{sys.platform}].')


def main():
    if not InstallationChecker.check():
        sys.exit(1)
    if not update_i18n_files(clean=False, generate_doc=False):
        logger.error('You must update the translations.')
        sys.exit(1)
    if not get_project_builder().run():
        logger.error('Export failed.')
        sys.exit(1)


if __name__ == '__main__':
    main()
