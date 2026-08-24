import ctypes
import os
from pathlib import Path

from packaging.version import Version
from requests import get, RequestException

from common import TMP_DIR
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from common.updaters.version_updater import VersionUpdater


logger = get_logger()


class WindowsUpdater:
    """Wrapper for the Windows updater"""

    @staticmethod
    def latest_version() -> Version:
        version = VersionUpdater.LATEST_VERSION
        assert version is not None
        return version

    @staticmethod
    def dev_exe_path() -> Path | None:
        """Env variable set in dev to bypass the requirement to download a published updater."""
        dev_exe = os.getenv('DEV_WINDOWS_UPDATER_PATH')
        if dev_exe:
            exe_path = Path(dev_exe)
            if exe_path.exists():
                return exe_path
            logger.error('Dev updater exe path [%s] not found.')
        return None

    @classmethod
    def exe_path(cls) -> Path:
        dev_exe = cls.dev_exe_path()
        if dev_exe:
            return dev_exe
        return TMP_DIR / VersionUpdater.get_asset_name(cls.latest_version())

    @classmethod
    def download(cls) -> bool:
        """Downloads the updater, returns True if successful."""
        if cls.dev_exe_path():
            # Downloading bypassed in dev
            return True
        exe_path = cls.exe_path()
        if exe_path.exists():
            return True
        url = VersionUpdater.get_asset_url(cls.latest_version())
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
    def run(cls):
        exe = str(cls.exe_path())
        locale = SharlyChessConfig().locale
        log_path = TMP_DIR / 'update.log'
        params = ['/SILENT', '/NOCANCEL', f'/LANG={locale}', f'/LOG="{log_path}"']
        # Type error when not running on windows
        ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, 'runas', exe, ' '.join(params), None, 1
        )
        # Terminate this process immediately. ShellExecuteW only *launches* the
        # elevated updater; if we return to the normal shutdown path, the running
        # executable and its _internal DLLs stay locked long enough that Inno
        # Setup skips the in-use files (the .exe isn't overwritten). Hard-exiting
        # releases the locks before the updater reaches its file-copy phase.
        os._exit(0)
