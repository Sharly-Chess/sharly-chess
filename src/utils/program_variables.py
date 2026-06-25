import os
import plistlib
import sys
from enum import StrEnum
from pathlib import Path


# OS-specific Paths
MACOS_SUPPORT_DIR = (
    Path.home() / 'Library' / 'Application Support' / 'com.sharlychess.thp'
)
MACOS_DATA_PLIST = MACOS_SUPPORT_DIR.parent / 'com.sharlychess.plist'
MACOS_DATA_PLIST.parent.mkdir(parents=True, exist_ok=True)

LINUX_ENV_FILE = Path.home() / '.bashrc'
WIN_REG_PATH = r'Software\Sharly Chess\Sharly Chess'


class ProgramVar(StrEnum):
    """Enum containing all the program variables.
    These variables are stored at a user-level static path,
    and must be considered requiring a restart to be refreshed."""

    DATA_DIR = 'data_directory'
    PREVIOUS_DATA_DIR = 'previous_data_directory'

    @property
    def stored_name(self) -> str:
        """Name used to store the variable."""
        from common import DEVEL_ENV

        name = self.value
        if DEVEL_ENV:
            # Prefix variables in dev to prevent impacting the prod env of the developer
            name = f'dev_{name}'
        if sys.platform == 'linux':
            # As linux uses env variables add an app specific prefix
            name = f'SHARLY_CHESS_{name.upper()}'
        return name

    def read_value(self) -> str | None:
        name = self.stored_name
        match sys.platform:
            case 'win32':
                import winreg

                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_REG_PATH) as key:
                        value, reg_type = winreg.QueryValueEx(key, name)
                        return str(value) if value else None
                except FileNotFoundError:
                    return None
            case 'darwin':
                return _read_macos_data_plist().get(name)
            case 'linux':
                return os.getenv(name)
        return None

    def clear_value(self):
        name = self.stored_name
        match sys.platform:
            case 'win32':
                # winreg.deleteValue requires admin priviledges, set empty value instead
                self.write_value('')
            case 'darwin':
                data = _read_macos_data_plist()
                if data.pop(name, None) is not None:
                    _write_macos_data_plist(data)
            case 'linux':
                self.write_value('')

    def write_value(self, value: str):
        self.write_variables({self: value})

    @classmethod
    def write_variables(cls, value_by_var: dict['ProgramVar', str]):
        match sys.platform:
            case 'win32':  # Use windows registries
                import winreg

                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_REG_PATH) as key:
                    for var, value in value_by_var.items():
                        winreg.SetValueEx(key, var.stored_name, 0, winreg.REG_SZ, value)
            case 'darwin':  # Use Plist
                data = _read_macos_data_plist()
                for var, value in value_by_var.items():
                    data[var.stored_name] = value
                _write_macos_data_plist(data)
            case 'linux':  # Use env variables
                with open(LINUX_ENV_FILE, 'a') as f:
                    for var, value in value_by_var.items():
                        f.write(f'\nexport {var.stored_name}="{value}"\n')


def _read_macos_data_plist() -> dict:
    try:
        with open(MACOS_DATA_PLIST, 'rb') as plist_file:
            return plistlib.load(plist_file)
    except (FileNotFoundError, OSError, plistlib.InvalidFileException):
        return {}


def _write_macos_data_plist(data: dict):
    with open(MACOS_DATA_PLIST, 'wb') as plist_file:
        plistlib.dump(data, plist_file)
