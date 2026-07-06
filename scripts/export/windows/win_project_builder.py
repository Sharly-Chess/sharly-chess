import json
import os
import shutil
import sys
from argparse import ArgumentParser, Namespace
from logging import Logger
from pathlib import Path
from typing import Any

from common import SHARLY_CHESS_VERSION
from common.installation_checker import InstallationChecker
from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()

# The release of SignTool installed by the GitHub action
SIGNTOOL_RELEASE: int = 26100

# The URL where to get the timestamp of the signature
SIGNTOOL_TIMESTAMP_URL = 'http://time.certum.pl'


class WinProjectBuilder(ProjectBuilder):
    """Windows specific class to export the project."""

    def __init__(self):
        # The fingerprint of the certificate used to sign files
        self.signtool_cert_fingerprint: str = ''
        super().__init__(clean_project_on_exit=True)
        self.exe_filename: str = self.basename + '.exe'
        self.exe: Path = self.project_dir / self.exe_filename
        signtool_version: str = f'10.0.{SIGNTOOL_RELEASE}.0'
        self.signtool_dir: Path = Path(
            f'C:/Program Files (x86)/Windows Kits/10/bin/{signtool_version}/x64'
        )
        self.signtool_exe: Path = self.signtool_dir / 'signtool.exe'

    def hook_extend_sys_path(
        self,
    ):
        sys.path.append(str(self.signtool_dir))

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

    def hook_post_clean_on_startup(self):
        # Will be used later to delete the MSI
        pass

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
            if not self.signtool_exe.is_file():
                logger.error(
                    f'SignTool program [{self.signtool_exe}] not found, please install the Windows Software Development Kit (SDK) to sign files (details at https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).'
                )
                return False
            if not self._sign_files():
                return False
        return True

    def _generate_control_files(self):
        tmp_dir = self.project_dir / 'tmp'
        tmp_dir.mkdir(exist_ok=True, parents=True)
        blocker = tmp_dir / '.direct-download-blocker'
        logger.info('Adding direct download blocker [%s]...', blocker)
        blocker.touch()
        control_file = tmp_dir / 'control_file.json'
        logger.info('Creating control file [%s]...', control_file)
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
        os.chdir(cwd)
        with open(control_file, 'w', encoding='utf-8') as file:
            json.dump(control_data, file)

    def _rename_executable_file(self):
        shutil.move(
            self.project_dir / f'{self.basename}.exe',
            self.project_dir / f'{self.project_name}.exe',
        )

    @staticmethod
    def _compact_command_output(
        output: str,
    ) -> str:
        return '\n'.join(
            line for line in map(lambda s: s.rstrip(), output.split('\n')) if line
        )

    def _signtool_command(
        self,
        params: list[str],
    ) -> tuple[int, str, str]:
        """Run SignTool and return the result code, stdout and stderr as strings"""
        # windows_tools.signtool has no sha1 parameter, needed to sign with
        # a cloud certificate, so the module can not be used.
        # from windows_tools.signtool import SignTool
        # signer: SignTool = SignTool(authority_timestamp_url='http://time.certum.pl')
        # signer.sign(EXE, bitness=64)

        import subprocess

        cmd: list[str] = [
            str(self.signtool_exe),
        ] + params
        logger.info('Running command [%s]...', ' '.join(cmd))
        process = subprocess.run(cmd, capture_output=True, text=True)
        logger.info('Command returned [%d].', process.returncode)

        return (
            process.returncode,
            self._compact_command_output(process.stdout),
            self._compact_command_output(process.stderr),
        )

    def _signtool_verify_file(
        self,
        file: Path,
        signed: bool,
    ) -> bool:
        """Verify if a file is signed or not signed, return True if as expected.
        Cf https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature"""
        logger.info(
            'Verifying that file [%s] is %s...',
            file,
            'signed' if signed else 'not signed',
        )
        result, out, err = self._signtool_command(
            [
                'verify',
                '-pa',
                '-v',
                str(file),
            ],
        )
        correct: bool
        if signed:
            correct = result == 0
        else:
            correct = result != 0
        if correct:
            logger.info(out)
            logger.info(
                'File [%s] is signed.' if signed else 'File [%s] is not signed.', file
            )
        else:
            logger.info(out)
            logger.warning(err)
            logger.error(
                'File [%s] is not signed.'
                if signed
                else 'File [%s] is already signed.',
                file,
            )
        return correct

    def _signtool_sign_file(
        self,
        file: Path,
    ) -> bool:
        """Sign the exe, return True if no error while signing."""
        logger.info('Signing file [%s]...', file)
        result, out, err = self._signtool_command(
            [
                'sign',
                '-sha1',
                self.signtool_cert_fingerprint,
                '-tr',
                SIGNTOOL_TIMESTAMP_URL,
                '-td',
                'sha256',
                '-fd',
                'sha256',
                str(file),
            ]
        )
        correct: bool = result == 0
        if correct:
            logger.info(out)
            logger.info('File [%s] has been successfully signed.', file)
        else:
            logger.info(out)
            logger.warning(err)
            logger.error('Signing file [%s] failed.', file)
        return correct

    def _sign_file(
        self,
        file: Path,
    ) -> bool:
        # Verify that the file is not already signed
        if not self._signtool_verify_file(file, signed=False):
            return True
        # Sign the file
        if not self._signtool_sign_file(file):
            return False
        # Verify that it has been signed
        if not self._signtool_verify_file(file, signed=True):
            return False
        return True

    def _sign_files(self) -> bool:
        files = [self.exe]
        for exe_installer in InstallationChecker.executable_installers:
            files += exe_installer.files_to_sign
        return all(self._sign_file(file) for file in files)
