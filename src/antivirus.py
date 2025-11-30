import json
import os
import platform
import subprocess
import sys
from abc import ABC
from logging import Logger
from pathlib import Path


from common import DEVEL_ENV, TMP_DIR
from common.logger import get_logger
from common.tool_installer import UACInstaller

logger: Logger = get_logger()


def search_missing_files(
    folder: Path,
):
    import sys

    if (
        platform.system() == 'Windows'
        and getattr(sys, 'frozen', False)
        and os.getenv('TEST_ENV') != 'true'
        and Path(sys.argv[0]).stem != 'pytest'
    ):
        # Microsoft Defender sometimes sends files to quarantaine when unzipping downloaded archives.
        control_file: Path = folder / 'tmp/control_file.json'
        if control_file.is_file():
            import json
            from typing import Any

            with open(control_file, 'r', encoding='utf8') as infile:
                control_data: dict[str, Any] = json.loads(infile.read())
            version: list[str] = control_data['version']
            file_paths: list[str] = control_data['file_paths']
            missing_files: list[str] = [
                file_path
                for file_path in file_paths
                if not (folder / file_path).is_file()
            ]
            if missing_files:
                import sys

                message: str = '\n'.join(
                    [
                        'Sharly Chess can not start because the following files are missing:',
                    ]
                    + [f'- {missing_file}' for missing_file in missing_files]
                    + [
                        'This is probably due to Windows Defender or any other antivirus sending files to quarantaine.',
                        'Recover the missing files from your quarantaine folder (depends on the antivirus you use) or manually install:',
                        f'1. Download Sharly Chess from https://github.com/Sharly-Chess/sharly-chess/releases/download/{version}/sharly-chess-{version}-windows.zip',
                        '2. Unzip the downloaded archive manually',
                    ]
                )
                import tkinter
                from tkinter import messagebox

                root = tkinter.Tk()
                root.withdraw()
                messagebox.showerror('Sharly Chess startup error', message)
                root.destroy()
                sys.exit(1)
            # Remove the control file not to check twice when no missing file the first time.
            control_file.unlink()


class UAC:
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

    def avast_exclude_sharly_chess_folder(
        self,
        folder: Path,
    ):
        """Calls the Sharly Chess UAC to add an Avast exclusion on the given folder."""
        self._exclude_sharly_chess_folder(
            folder,
            '--avast-exclude',
        )


# https://unprotect.it/snippet/adding-antivirus-exception/241/
class Antivirus(ABC):
    def __init__(
        self,
        name: str,
        signatures: list[str],
    ):
        self.name = name
        self.signatures: list[str] = signatures
        self.tmp_dir = TMP_DIR / 'antivirus'
        self.tmp_dir.mkdir(exist_ok=True)

    def run(
        self,
        folder: Path,
    ) -> None:
        """Executes an action to prevent the antivirus from interfering with the program's execution."""
        pass


if (
    platform.system() == 'Windows'
    and os.getenv('TEST_ENV') != 'true'
    and Path(sys.argv[0]).stem != 'pytest'
):

    class WindowsAntivirus(Antivirus):
        def __init__(
            self,
            name: str,
            signatures: list[str],
        ):
            super().__init__(name, signatures)

    class WindowsDefender(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Windows Defender',
                [
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
                logger.warning(
                    'Environment variable [%s] not set.', program_files_var_name
                )
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
                f'{folder}\\|*',
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
                    folder = folder.absolute()
                if self._folder_excluded(mpcmdrun_exe, folder.absolute()):
                    logger.debug(
                        'Folder [%s] already belongs to the Windows Defender exclusions.',
                        folder,
                    )
                elif UACInstaller().is_installed:
                    logger.info(
                        'Calling Sharly Chess UAC to add Sharly Chess folder to the Windows Defender exclusions...'
                    )
                    UAC().windows_defender_exclude_sharly_chess_folder(folder)
                elif DEVEL_ENV:
                    logger.info(
                        'Sharly Chess UAC not installed yet, can not add Sharly Chess folder to the Windows Defender exclusions.'
                    )

    class Avast(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Avast',
                [
                    'snxhk.dll',
                    'sf2.dll',
                    'AvastUI.exe',
                    'aswToolsSvc.exe',
                    'aswEngSrv.exe',
                    'afwServ.exe',
                    'wsc_proxy.exe',
                    'AvastSvc.exe',
                    'aswidsagent.exe',
                ],
            )

        def run(
            self,
            folder: Path,
        ) -> None:
            # There is no way like with Windows Defender to know if the Sharly Chess folder
            # already belongs to the Avast exclusions. So the best we can do is always calling
            # UAC and marking the folder as excluded not to do it twice (if the user removes
            # the exclusion we assume (s)he knows what (s)he does).
            marker_file: Path = self.tmp_dir / f'{self.name}.json'
            if not folder.is_absolute():
                folder = folder.absolute()
            if marker_file.is_file():
                with open(marker_file, 'r', encoding='utf-8') as file:
                    marked_folder: str = json.load(file)
                    if marked_folder == str(folder):
                        logger.debug(
                            'Folder [%s] has already been add to the Avast exclusions.',
                            folder,
                        )
                        return
            if UACInstaller().is_installed:
                logger.info(
                    'Calling Sharly Chess UAC to add Sharly Chess folder to the Avast exclusions...'
                )
                UAC().avast_exclude_sharly_chess_folder(folder)
            elif DEVEL_ENV:
                logger.info(
                    'Sharly Chess UAC not installed yet, can not add Sharly Chess folder to the Avast exclusions.'
                )

    class AVG(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'AVG',
                [
                    'avghookx.dll',
                    'avghooka.dll',
                ],
            )

    class Sandboxie(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Sandboxie',
                [
                    'sbiedll.dll',
                ],
            )

    class WindBG(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'WindDB',
                [
                    'dbghelp.dll',
                ],
            )

    class IDefenseLab(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'iDefense Lab',
                [
                    'api_log.dll',
                    'dir_watch.dll',
                ],
            )

    class SunbeltSandbox(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'SunBelt Sandbox',
                [
                    'pstorec.dll',
                ],
            )

    class VirtualPC(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Virtual PC',
                [
                    'vmcheck.dll',
                ],
            )

    class WPEPro(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'WPE Pro',
                [
                    'wpespy.dll',
                ],
            )

    class ComodoContainer(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Comodo Container',
                [
                    'cmdvrt64.dll',
                    'cmdvrt32.dll',
                ],
            )

    class Software360(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                '360 SOFTWARE',
                [
                    'sxin.dll',
                ],
            )

    class UnknownSandbox(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Unknown Sandbox',
                [
                    'printfhelp.dll',
                ],
            )

    class ESET(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'ESET',
                [
                    'ekrn.exe',
                ],
            )

    class Avira(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Avira',
                [
                    'avguard.exe',
                    'avscan.exe',
                ],
            )

    class Norton(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Norton',
                [
                    'ccSvcHst.exe',
                    'norton.exe',
                ],
            )

    class McAfee(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'McAfee',
                [
                    'mcshield.exe',
                    'mcupdate.exe',
                ],
            )

    class FSecure(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'F-Secure',
                [
                    'fsav.exe',
                    'fsgk32.exe',
                ],
            )

    class Kaspersky(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Kaspersky',
                [
                    'kav.exe',
                    'kavsvc.exe',
                ],
            )


def detect_antivirus(
    folder: Path,
) -> list[Antivirus]:
    """Detect antivirus programs running on the server and add exclusions for the given folder when possible."""
    if (
        platform.system() == 'Windows'
        and os.getenv('TEST_ENV') != 'true'
        and Path(sys.argv[0]).stem != 'pytest'
    ):
        import psutil

        detected_antivirus_programs: list[Antivirus] = []
        try:
            logger.debug('Analysing running processes...')
            process_names: list[str] = [
                process.info['name'].lower()
                for process in psutil.process_iter(attrs=['name'])
            ]
            for avs in [
                WindowsDefender(),
                Avast(),
                AVG(),
                Sandboxie(),
                WindBG(),
                IDefenseLab(),
                SunbeltSandbox(),
                VirtualPC(),
                WPEPro(),
                ComodoContainer(),
                Software360(),
                UnknownSandbox(),
                ESET(),
                Avira(),
                Norton(),
                McAfee(),
                FSecure(),
                Kaspersky(),
            ]:
                for signature in avs.signatures:
                    if signature.lower() in process_names:
                        logger.debug(
                            'Process [%s] identifies antivirus [%s].',
                            signature,
                            avs.name,
                        )
                        detected_antivirus_programs.append(avs)
                        break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            logger.warning('Could not detect antivirus programs: %s', e)
        if detected_antivirus_programs:
            logger.debug('The following antivirus programs have been detected:')
            for detected_antivirus_program in detected_antivirus_programs:
                logger.debug('- %s', detected_antivirus_program.name)
            for detected_antivirus_program in detected_antivirus_programs:
                logger.debug(
                    'Running action for [%s]...', detected_antivirus_program.name
                )
                detected_antivirus_program.run(folder or Path())
        else:
            logger.debug('No antivirus program has been detected.')
        return detected_antivirus_programs
    else:
        return []
