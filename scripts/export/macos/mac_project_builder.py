from logging import Logger
import os
from pathlib import Path
import sys

from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class MacProjectBuilder(ProjectBuilder):
    """MacOS specific class to export the project."""

    def __init__(self):
        # Do not clean the project folder to sign files with script build_and_notarize.sh
        super().__init__(clean_project_on_exit=False)

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return [
            '--windowed',  # Create macOS app bundle
            f'--osx-bundle-identifier=com.{self.project_name}.app',
            f'--icon=src/web/static/images/{self.project_name}.icns',
        ]

    @property
    def _python_dir(self) -> Path:
        """Returns the base dir for Python."""
        try:
            # devel
            return Path(os.environ['VIRTUAL_ENV']) / 'bin'
        except KeyError:
            # GitHub
            return Path(sys.executable).parent

    @property
    def hook_get_venv_lib_path(
        self,
    ) -> Path:
        return self._python_dir / '..' / 'lib' / 'python3.12' / 'site-packages'

    def hook_post_build_project(self) -> bool:
        # The SharlyChess.app bundle is now created by the build_and_notarize.sh script
        # No longer need to create Launch Sharly Chess.app here
        logger.info(
            'Skipping launcher creation (will be handled by build_and_notarize.sh)'
        )
        return True
