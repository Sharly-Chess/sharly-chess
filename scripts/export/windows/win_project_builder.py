import os
from logging import Logger
from pathlib import Path

from common import SHARLY_CHESS_VERSION
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()

# The release of SignTool installed by the GitHub action
SIGNTOOL_RELEASE: int = 26100

# The fingerprint of the certificate used to signe the EXE
SIGNTOOL_CERT_FINGERPRINT: str = '93ce5c3718b4ac7471f6697bf4693d5ed985046e'

# The URL where to get the timestamp of the signature
SIGNTOOL_TIMESTAMP_URL = 'http://time.certum.pl'


class WinProjectBuilder(ProjectBuilder):
    """Windows specific class to export the project."""

    def __init__(self):
        super().__init__(clean_project_on_exit=True)
        self.exe_filename: str = self.basename + '.exe'
        self.exe: Path = self.project_dir / self.exe_filename
        signtool_version: str = f'10.0.{SIGNTOOL_RELEASE}.0'
        self.signtool_dir: Path = Path(
            f'C:/Program Files (x86)/Windows Kits/10/bin/{signtool_version}/x64'
        )

    def hook_post_clean_on_startup(self):
        # Will be used later to delete the MSI
        pass

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return []

    def hook_post_build_project(self) -> bool:
        if not self.sign_exe():
            return False
        if not self._build_chessevent_batch():
            return False
        return True

    def _signtool_command(
        self,
        params: list[str],
    ) -> int:
        # windows_tools.signtool has no sha1 parameter
        # from windows_tools.signtool import SignTool
        # signer: SignTool = SignTool(authority_timestamp_url='http://time.certum.pl')
        # signer.sign(EXE, bitness=64)

        import subprocess

        cmd: list[str] = [
            str(self.signtool_dir / 'signtool.exe'),
        ] + params
        logger.info(f'Running {" ".join(cmd)}')
        process = subprocess.run(cmd, capture_output=True, text=True)
        for line in map(lambda s: s.rstrip(), process.stdout.split('\n')):
            if line:
                logger.info(line)
        for line in map(lambda s: s.rstrip(), process.stderr.split('\n')):
            if line:
                logger.error(line)
        return process.returncode

    def _signtool_verify_exe(self) -> bool:
        """Verify the exe, return True if correctly signed."""
        # https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature
        return (
            self._signtool_command(
                [
                    'verify',
                    '-pa',
                    '-v',
                    str(self.exe),
                ]
            )
            == 0
        )

    def _signtool_sign_exe(self) -> bool:
        """Sign the exe, return True if no error while signing."""
        return (
            self._signtool_command(
                [
                    'sign',
                    '-sha1',
                    str(SIGNTOOL_CERT_FINGERPRINT),
                    '-tr',
                    str(SIGNTOOL_TIMESTAMP_URL),
                    '-td',
                    'sha256',
                    '-fd',
                    'sha256',
                    str(self.exe),
                ]
            )
            != 0
        )

    def sign_exe(self) -> bool:
        cwd = os.getcwd()
        # SignTool must run from its folder or the folder added to PATH
        os.chdir(self.signtool_dir)
        if self._signtool_verify_exe():
            logger.warning('Executable already signed.')
            return False
        logger.info('Signing file [%s]...', self.exe)
        if not self._signtool_sign_exe():
            logger.warning('Failed to sign the executable.')
            return False
        logger.info('Executable signed successfully.')
        logger.info('Verifying the signature...')
        if not self._signtool_verify_exe():
            logger.warning('Verification failed.')
            return False
        logger.info('Executable signature successfully verified..')
        os.chdir(cwd)
        return True

    def _build_chessevent_batch(self) -> bool:
        target_file = self.tools_dir / 'chessevent.bat'
        logger.info('Creating batch file [%s]]...', target_file)
        with open(target_file, 'wt', encoding='utf-8') as f:
            f.write(
                f'@echo off\n'
                f'echo Starting Sharly Chess ChessEvent client, please wait...\n'
                f'@rem Sharly Chess {SHARLY_CHESS_VERSION} - {SharlyChessConfig.en_copyright} - {SharlyChessConfig.url}\n'
                f'cd ..\n'
                f'{self.exe_filename} --chessevent\n'
                f'pause\n'
            )
        return True
