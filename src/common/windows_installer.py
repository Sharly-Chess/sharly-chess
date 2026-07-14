import ctypes
import os
from pathlib import Path

from packaging.version import Version
from requests import get, RequestException

from common import TMP_DIR
from common.logger import get_logger

logger = get_logger()


class WindowsInstaller:
    """Wrapper for the Windows Installer executable."""

    @staticmethod
    def dev_exe_path() -> Path | None:
        """Env variable set in dev to bypass the requirement to download a published setup."""
        dev_exe = os.getenv('DEV_WINDOWS_INSTALLER_PATH')
        if dev_exe:
            exe_path = Path(dev_exe)
            if exe_path.exists():
                return exe_path
            logger.error('Dev updater exe path [%s] not found.', dev_exe)
        return None

    @classmethod
    def exe_path(cls, version: Version) -> Path:
        dev_exe = cls.dev_exe_path()
        if dev_exe:
            return dev_exe
        return TMP_DIR / f'Sharly Chess Installer {version}.exe'

    @classmethod
    def download(cls, version: Version, url: str | None) -> bool:
        """Downloads the updater, returns True if successful."""
        if cls.dev_exe_path():
            # Downloading bypassed in dev
            return True
        exe_path = cls.exe_path(version)
        if exe_path.exists():
            return True
        if not url:
            logger.error('No Download URL provided.')
            return False
        try:
            response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            with open(exe_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except RequestException as ex:
            logger.error('An error occurred while requesting GitHub.')
            logger.debug('Failed to read [%s]: [%s].', url, ex)
            return False

    @classmethod
    def run(cls, version: Version):
        exe = str(cls.exe_path(version))
        # Type error when not running on windows
        ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, 'runas', exe, None, None, 1
        )
