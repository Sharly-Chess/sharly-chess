from logging import Logger
from pathlib import Path

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class WindowsDefender(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Windows Defender',
            doc_url='',
            signatures=[
                'msmpeng.exe',
                'mpcmdrun.exe',
            ],
        )

    @staticmethod
    def _get_mpcmdrun_exe() -> Path | None:
        """Returns the MpCmdRun executable or None."""
        import os

        program_files_var_name: str = 'ProgramFiles'
        if not (program_files_var := os.getenv(program_files_var_name)):
            logger.warning('Environment variable [%s] not set.', program_files_var_name)
            return None
        program_files_dir = Path(program_files_var)
        windows_defender_dir: Path = program_files_dir / 'Windows Defender'
        if not windows_defender_dir.is_dir():
            logger.warning('Folder [%s] not found.', windows_defender_dir)
            return None
        mpcmdrun_exe: Path = windows_defender_dir / 'MpCmdRun.exe'
        if not mpcmdrun_exe.is_file():
            logger.warning('Executable [%s] not found.', mpcmdrun_exe)
            return None
        return mpcmdrun_exe

    @staticmethod
    def _folder_excluded(
        mpcmdrun_exe: Path,
        folder: Path,
    ) -> bool:
        """Returns True if the folder is excluded by Windows Defender"""

        # https://blog.fndsec.net/2024/10/04/uncovering-exclusion-paths-in-microsoft-defender-a-security-research-insight/#using-mpcmdrun-exe-to-identify-exclusions
        # It is not possible with user privileges to get the list of all the Windows Defender
        # exclusions so we just try to scan Sharly Chess folder and propose to add an exclusion on it.
        import subprocess

        cmd: list[str] = [
            str(mpcmdrun_exe),
            '-Scan',
            '-ScanType',
            '3',
            '-File',
            f'{folder.resolve()}\\|*',
        ]
        logger.debug('Running command [%s]...', ' '.join(cmd))
        process = subprocess.run(cmd, capture_output=True, text=True)
        logger.debug('Command returned [%d].', process.returncode)
        logger.debug(
            'stdout=%s',
            '\n'.join(
                line
                for line in map(lambda s: s.rstrip(), process.stdout.split('\n'))
                if line
            ),
        )
        logger.debug(
            'stderr=%s',
            '\n'.join(
                line
                for line in map(lambda s: s.rstrip(), process.stderr.split('\n'))
                if line
            ),
        )
        success: bool = process.returncode == 0
        if not success:
            logger.debug(
                'Scan failed, folder [%s] is not excluded by Windows Defender.',
                folder,
            )
        else:
            logger.debug(
                'Scan succeeded, folder [%s] is already excluded by Windows Defender.',
                folder,
            )
        return success

    def run(
        self,
        folder: Path,
    ) -> None:
        if mpcmdrun_exe := self._get_mpcmdrun_exe():
            if not folder.is_absolute():
                folder = folder.resolve()
            if self._folder_excluded(mpcmdrun_exe, folder.resolve()):
                logger.debug(
                    'Folder [%s] already belongs to the Windows Defender exclusions.',
                    folder,
                )
            else:
                super().run(folder)
