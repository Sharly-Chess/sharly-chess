import argparse
import ctypes
import sys
import winreg
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal, Any
from winreg import HKEYType


class WindowsRegistryUtils:
    @classmethod
    def _set_registry_value(
        cls,
        key: HKEYType | int,
        sub_key: str,
        name: str,
        type: Literal[4, 5] | int,
        value: Any,
    ) -> bool:
        """Sets the value of an entry of the registry, returns True on success, False on failure"""
        try:
            winreg.CreateKey(key, sub_key)
            registry_key = winreg.OpenKey(
                key,
                sub_key,
                0,
                winreg.KEY_WRITE,
            )
            winreg.SetValueEx(
                registry_key,
                name,
                0,
                type,
                value,
            )
            winreg.CloseKey(registry_key)
            return True
        except WindowsError as we:
            print(
                f'{cls.__name__}.set_registry_value(key=[{key}], sub_key=[{sub_key}], name=[{name}], value=[{value}]) raised an error: {we}'
            )
            return False

    @classmethod
    def _set_registry_hklm_value(
        cls,
        sub_key: str,
        name: str,
        type: Literal[4, 5] | int,
        value: Any,
    ) -> bool:
        return cls._set_registry_value(
            winreg.HKEY_LOCAL_MACHINE, sub_key, name, type, value
        )

    @classmethod
    def set_registry_hklm_dword(
        cls,
        sub_key: str,
        name: str,
        value: Any,
    ) -> bool:
        return cls._set_registry_hklm_value(sub_key, name, winreg.REG_DWORD, value)

    @classmethod
    def _get_registry_value(
        cls,
        key: HKEYType | int,
        sub_key: str,
        name: str,
    ) -> Any:
        try:
            registry_key = winreg.OpenKey(
                key,
                sub_key,
                0,
                winreg.KEY_READ,
            )
            value, regtype = winreg.QueryValueEx(registry_key, name)
            winreg.CloseKey(registry_key)
            return value
        except WindowsError as we:
            print(
                f'{cls.__name__}.get_registry_value(key=[{key}], sub_key=[{sub_key}], name=[{name}]) raised an error: {we}'
            )
            return None

    @classmethod
    def get_registry_hklm_value(
        cls,
        sub_key: str,
        name: str,
    ) -> Any:
        return cls._get_registry_value(winreg.HKEY_LOCAL_MACHINE, sub_key, name)

    @classmethod
    def get_registry_hkcu_value(
        cls,
        sub_key: str,
        name: str,
    ) -> Any:
        return cls._get_registry_value(winreg.HKEY_CURRENT_USER, sub_key, name)

    @classmethod
    def _get_registry_values(
        cls,
        key: HKEYType | int,
        sub_key: str,
    ) -> dict[str, Any]:
        key_dict = {}
        i = 0
        try:
            registry_key = winreg.OpenKey(key, sub_key, 0, winreg.KEY_READ)
            while True:
                try:
                    subvalue = winreg.EnumValue(registry_key, i)
                except WindowsError:
                    break
                key_dict[subvalue[0]] = subvalue[1:]
                i += 1
            return key_dict
        except WindowsError as we:
            print(
                f'{cls.__name__}.get_registry_values(key=[{key}], sub_key=[{sub_key}]) raised an error: {we}'
            )
            return key_dict

    @classmethod
    def get_registry_hklm_values(
        cls,
        sub_key: str,
    ) -> dict[str, Any]:
        return cls._get_registry_values(winreg.HKEY_LOCAL_MACHINE, sub_key)

    @classmethod
    def get_registry_hkcu_values(
        cls,
        sub_key: str,
    ) -> dict[str, Any]:
        return cls._get_registry_values(winreg.HKEY_CURRENT_USER, sub_key)


class UAC(ABC):
    """An abstract class that asks for admin privileges to execute its run() method."""

    def run_as_admin(self):
        """Runs with administrator rights, cf https://stackoverflow.com/questions/130763/request-uac-elevation-from-within-a-python-script/41930586#41930586"""
        admin: bool = False
        try:
            admin = ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            pass
        if not admin:
            if error := self._user_check():
                self._exit_on_error(error)
            ctypes.windll.shell32.ShellExecuteW(
                None, 'runas', sys.executable, ' '.join(sys.argv), None, 1
            )
        else:
            if error := self._admin_check():
                self._exit_on_error(error)
            if error := self._run():
                self._exit_on_error(error)

    @staticmethod
    def _exit_on_error(
        message: str,
    ):
        """This method should be called on error to exit the program."""
        print(f'Error: {message}')
        input('Type Enter to close this window.')
        sys.exit(1)

    def _user_check(self) -> str | None:
        """Checks that everything is good before asking to run with administrator rights.
        Returns an error message on failure or None on success."""
        return None

    def _admin_check(self) -> str | None:
        """Checks that everything is good once running with administrator rights.
        Returns an error message on failure or None on success."""
        return None

    @abstractmethod
    def _run(self) -> str | None:
        """Does the job (with administrator rights).
        Returns an error message on failure or None on success."""
        pass


class WindowsDefenderUAC(UAC):
    def __init__(
        self,
        folder: str,
    ):
        super().__init__()
        self.folder = folder.rstrip('\\')

    @staticmethod
    def get_exclusions() -> list[str]:
        """Returns all Windows Defender exclusions."""
        return list(
            WindowsRegistryUtils.get_registry_hklm_values(
                r'SOFTWARE\Microsoft\Windows Defender\Exclusions\Paths'
            ).keys()
        )

    def add_exclusion(self) -> bool:
        """Add the folder to Windows defender exclusions.
        Returns True on success, False on failure."""
        import subprocess

        cmd: list[str] = [
            'powershell',
            '-Command',
            f'Add-MpPreference -ExclusionPath "{self.folder}"',
        ]
        print(
            f'Running command [{" ".join(cmd)}]...',
        )
        process = subprocess.run(cmd, capture_output=True, text=True)
        print(f'Command returned [{process.returncode}].')
        print(
            f'stdout={"\n".join(line for line in map(lambda s: s.rstrip(), process.stdout.split("\n")) if line)}'
        )
        print(
            f'stderr={"\n".join(line for line in map(lambda s: s.rstrip(), process.stderr.split("\n")) if line)}'
        )
        return process.returncode == 0

    def _user_check(self) -> str | None:
        if not Path(self.folder).is_dir():
            return f'[{sys.argv[0]}] Folder {self.folder} not found.'
        return None

    def _admin_check(self) -> str | None:
        if error := self._user_check():
            return error
        if self.folder in self.get_exclusions():
            return (
                f'Folder [{self.folder}] is already in the Windows Defender exclusions.'
            )
        return None

    def _run(self) -> str | None:
        if not self.add_exclusion():
            return f'Could not add folder [{self.folder}] to the Windows Defender exclusions.'
        print('Windows Defender exclusions have been updated:')
        for exclusion in self.get_exclusions():
            print(f'- {exclusion}')
        return None


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--windows-defender-exclude', type=str)
    args = parser.parse_args()
    if args.windows_defender_exclude:
        WindowsDefenderUAC(args.windows_defender_exclude).run_as_admin()
    else:
        input(f'[{sys.argv[0]}]: no parameter provided.')
        sys.exit(1)


if __name__ == '__main__':
    main()
