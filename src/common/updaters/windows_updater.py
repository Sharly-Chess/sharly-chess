import ctypes
from pathlib import Path


from common import BASE_DIR
from common.sharly_chess_config import SharlyChessConfig
from common.tool_installer import SCWinUpdaterInstaller


class WindowsUpdater:
    """Wrapper for the Windows updater.
    See https://github.com/Sharly-Chess/sc-win-updater"""

    @staticmethod
    def executable_path() -> Path:
        return SCWinUpdaterInstaller().executable_path

    @classmethod
    def run(cls):
        config = SharlyChessConfig()
        params = ['-l', config.locale, '-o', f'"{BASE_DIR.parent}"']
        if config.check_beta_versions:
            params.append('-b')
        exe = str(cls.executable_path())
        ctypes.windll.shell32.ShellExecuteW(
            None, 'runas', exe, ' '.join(params), None, 1
        )
