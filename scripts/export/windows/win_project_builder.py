import os
import shutil
import sys
from logging import Logger
from pathlib import Path

from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class WinProjectBuilder(ProjectBuilder):
    """Windows specific class to export the project."""

    def __init__(self):
        super().__init__()
        self.exe = self.project_dir / f'{self.project_name}.exe'

    @property
    def _python_dir(self) -> Path:
        """Returns the base dir for Python."""
        try:
            # devel
            return Path(os.environ['VIRTUAL_ENV'])
        except KeyError:
            # GitHub
            return Path(sys.executable).parent

    @property
    def hook_get_venv_lib_path(
        self,
    ) -> Path:
        return self._python_dir / 'Lib' / 'site-packages'

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return [
            # TODO Used for MacOS and Windows, move this to a normal option if also needed on Linux.
            '--windowed',
            f'--icon=src/web/static/images/{self.project_name}.ico',
        ]

    def _rename_executable_file(self):
        shutil.move(self.project_dir / f'{self.basename}.exe', self.exe)
