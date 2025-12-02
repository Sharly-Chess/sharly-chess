import subprocess
from logging import Logger
from pathlib import Path

from common.logger import get_logger
from common.tool_installer import UACInstaller

logger: Logger = get_logger()


class UACWrapper:
    """Wrapper on the Sharly Chess UAC
    (see https://github.com/Sharly-Chess/sharly-chess-uac)"""

    @property
    def executable_path(self) -> Path:
        return UACInstaller().executable_path

    def _exclude_sharly_chess_folder(
        self,
        folder: Path,
        option_name: str,
    ):
        """Calls the Sharly Chess UAC to add an exclusion on the Sharly Chess folder."""
        cmd: list[str] = [
            str(self.executable_path),
            option_name,
            str(folder),
        ]
        logger.debug('Running command [%s]...', ' '.join(cmd))
        process = subprocess.run(cmd, capture_output=True, text=True)
        logger.debug('Command returned [%d].', process.returncode)
        if stdout_str := '\n'.join(
            line
            for line in map(lambda s: s.rstrip(), process.stdout.split('\n'))
            if line
        ):
            logger.debug(stdout_str)
        if stderr_str := '\n'.join(
            line
            for line in map(lambda s: s.rstrip(), process.stderr.split('\n'))
            if line
        ):
            logger.warning(stderr_str)
        return process.returncode == 0

    def windows_defender_exclude_sharly_chess_folder(
        self,
        folder: Path,
    ):
        """Calls the Sharly Chess UAC to add a Windows Defender exclusion on the given folder."""
        self._exclude_sharly_chess_folder(
            folder,
            '--windows-defender-exclude',
        )
