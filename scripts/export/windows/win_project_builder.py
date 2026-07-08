import os
import shutil
import sys
from argparse import ArgumentParser, Namespace
from logging import Logger
from pathlib import Path

from common.installation_checker import InstallationChecker
from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder
from scripts.export.windows import signtool

logger: Logger = get_logger()


class WinProjectBuilder(ProjectBuilder):
    """Windows specific class to export the project."""

    def __init__(self):
        # The fingerprint of the certificate used to sign files
        self.signtool_cert_fingerprint: str = ''
        super().__init__()
        self.exe = self.project_dir / f'{self.project_name}.exe'

    def hook_add_params(
        self,
        parser: ArgumentParser,
    ):
        parser.add_argument(
            '--windows-signtool-cert-fingerprint',
            type=str,
            help='The user.',
        )

    def hook_check_params(
        self,
        args: Namespace,
    ):
        self.signtool_cert_fingerprint = args.windows_signtool_cert_fingerprint

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
        if self.signtool_cert_fingerprint:
            if not signtool.check_available():
                return False
            if not self._sign_files():
                return False
        return True

    def _rename_executable_file(self):
        shutil.move(self.project_dir / f'{self.basename}.exe', self.exe)

    def _sign_files(self) -> bool:
        files = [self.exe]
        for exe_installer in InstallationChecker.executable_installers:
            files += exe_installer.files_to_sign
        return all(
            signtool.sign_file(file, self.signtool_cert_fingerprint) for file in files
        )
