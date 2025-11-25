import os
import platform
import sys
from abc import ABC
from pathlib import Path


def control_files() -> None:
    import sys

    if (
        platform.system() == 'Windows'
        and getattr(sys, 'frozen', False)
        and os.getenv('TEST_ENV') != 'true'
        and Path(sys.argv[0]).stem != 'pytest'
    ):
        # Microsoft Defender sometimes sends files to quarantaine when unzipping downloaded archives.
        control_file: Path = Path('tmp', 'control_file.json')
        if control_file.is_file():
            import json
            from typing import Any

            with open(control_file, 'r', encoding='utf8') as infile:
                control_data: dict[str, Any] = json.loads(infile.read())
            version: list[str] = control_data['version']
            file_paths: list[str] = control_data['file_paths']
            missing_files: list[str] = [
                file_path for file_path in file_paths if not Path(file_path).is_file()
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


# https://unprotect.it/snippet/adding-antivirus-exception/241/
class Antivirus(ABC):
    def __init__(
        self,
        name: str,
        signatures: list[str],
    ):
        self.name = name
        self.signatures: list[str] = signatures

    def run(self) -> None:
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

            if not (program_files_var := os.getenv('ProgramFiles')):
                print('%ProgramFiles% not set.')
                return None
            program_files_dir = Path(program_files_var)
            windows_defender_dir: Path = program_files_dir / 'Windows Defender'
            if not windows_defender_dir.is_dir():
                print(f'Folder [{windows_defender_dir}] not found.')
                return None
            mpcmdrun_exe: Path = windows_defender_dir / 'MpCmdRun.exe'
            if not mpcmdrun_exe.is_file():
                print(f'Executable [{mpcmdrun_exe}] not found.')
                return None
            return mpcmdrun_exe

        @staticmethod
        def _folder_excluded(
            mpcmdrun_exe: Path,
            folder: Path,
        ) -> bool:
            """Returns True if the folder is excluded by Windows Defender"""

            import subprocess

            cmd: list[str] = [
                str(mpcmdrun_exe),
                '-Scan',
                '-ScanType',
                '3',
                '-File',
                f'{folder}\\|*',
            ]
            # print(f'Running command [{' '.join(cmd)}]...', )
            process = subprocess.run(cmd, capture_output=True, text=True)
            # print(f'Command returned [{process.returncode}].')
            # print(f'stdout={'\n'.join(line for line in map(lambda s: s.rstrip(), process.stdout.split('\n')) if line)}')
            # print(f'stderr={'\n'.join(line for line in map(lambda s: s.rstrip(), process.stderr.split('\n')) if line)}')
            return process.returncode == 0

        def run(self) -> None:
            # https://blog.fndsec.net/2024/10/04/uncovering-exclusion-paths-in-microsoft-defender-a-security-research-insight/#using-mpcmdrun-exe-to-identify-exclusions
            # It is not possible with user privileges to get the list of all the
            # Windows Defender exclusions so we just try to scan Sharly Chess
            # folder and propose to add an exclusion on it.
            if mpcmdrun_exe := self._get_mpcmdrun_exe():
                folder: Path = Path().absolute()
                if self._folder_excluded(mpcmdrun_exe, folder):
                    print(
                        f'Folder [{folder}] already belongs to the Windows Defender exclusions.'
                    )
                else:
                    print(
                        f'Folder [{folder}] should be added to the Windows Defender exclusions.'
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

    class Avast(WindowsAntivirus):
        def __init__(self):
            super().__init__(
                'Avast',
                [
                    'snxhk.dll',
                    'sf2.dll',
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


def detect_antivirus() -> list[Antivirus]:
    if (
        platform.system() == 'Windows'
        and os.getenv('TEST_ENV') != 'true'
        and Path(sys.argv[0]).stem != 'pytest'
    ):
        import psutil

        detected_antivirus_softwares: list[Antivirus] = []
        try:
            for proc in psutil.process_iter(attrs=['pid', 'name']):
                for avs in [
                    AVG(),
                    Avast(),
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
                    WindowsDefender(),
                ]:
                    for signature in avs.signatures:
                        if signature.lower() in proc.info['name'].lower():
                            detected_antivirus_softwares.append(avs)
                            break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            print(f'Could not detect antivirus softwares: {e}')
            pass
        if detected_antivirus_softwares:
            print('The following antivirus softwares have been detected:')
            for detected_antivirus_software in detected_antivirus_softwares:
                print(f'- {detected_antivirus_software.name}')
            for detected_antivirus_software in detected_antivirus_softwares:
                # print(f'Running action for {detected_antivirus_software.name}...')
                detected_antivirus_software.run()
        return detected_antivirus_softwares
    else:
        return []
