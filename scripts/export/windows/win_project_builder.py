import json
import os
import sys
from logging import Logger
from pathlib import Path
from typing import Any

from common import SHARLY_CHESS_VERSION
from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class WinProjectBuilder(ProjectBuilder):
    """Windows specific class to export the project."""

    def __init__(self):
        super().__init__(clean_project_on_exit=True)
        self.exe_filename: str = self.basename + '.exe'
        self.exe: Path = self.project_dir / self.exe_filename

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

    def hook_post_build_project(self) -> bool:
        Path(self.project_dir / 'tmp/.unblock_files').touch()
        return True

    def build_control_file(self) -> bool:
        logger.info('Creating control file [%s]...', self.control_file)
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        control_data: dict[str, Any] = {
            'version': str(SHARLY_CHESS_VERSION),
            'file_paths': [],
        }
        cwd: str = os.getcwd()
        os.chdir(self.project_dir)
        for folder_name, sub_folders, file_names in os.walk('.'):
            for filename in file_names:
                file_path: Path = Path(folder_name, filename)
                control_data['file_paths'].append(str(file_path))
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.control_file, 'w', encoding='utf-8') as file:
            json.dump(
                control_data,
                file,
            )
        os.chdir(cwd)
        return True
