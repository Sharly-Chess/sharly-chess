"""Generate the Setup and Updater .EXE files using the Inno Setup Command Compiler
Usage: Dev only (Prod uses GH actions to ease transition out of the windows runner dependency).
Tips: To try the behavior of the Setup files without compiling the full export, delete the `_internal` dir of the project build."""

import subprocess
import sys
from pathlib import Path

from common import SHARLY_CHESS_VERSION, BASE_DIR
from common.logger import get_logger

logger = get_logger()

IS_VERSION = 6
ISCC_EXE = Path(rf'C:\Program Files (x86)\Inno Setup {IS_VERSION}\ISCC.exe')
ISS_SCRIPT_FILE = BASE_DIR / 'windows-setup.iss'
UPDATER_EXE = BASE_DIR / 'export' / f'Sharly Chess Updater {SHARLY_CHESS_VERSION}.exe'
SETUP_EXE = BASE_DIR / 'export' / f'Sharly Chess Setup {SHARLY_CHESS_VERSION}.exe'
DIST_DIR = BASE_DIR / 'dist' / f'sharly-chess-{SHARLY_CHESS_VERSION}'


def _compact_cmd_output(output: str) -> str:
    return '\n'.join(
        line for line in map(lambda s: s.rstrip(), output.split('\n')) if line
    )


def check_available() -> bool:
    if not sys.platform == 'win32':
        logger.error('You are not using Windows.')
        return False
    if not ISCC_EXE.exists():
        logger.error(
            f'Inno Setup Compiler [{ISCC_EXE}] not found, please install Inno Setup '
            f'{IS_VERSION} (see https://jrsoftware.org/isdl.php/Inno-Setup-Downloads).'
        )
        return False
    if not DIST_DIR.exists():
        logger.error(
            f'Project has to be built at [{DIST_DIR}] before generating the '
            f'setup files.\nTo do so, you have to run scripts/export/build.py.'
        )
        return False
    return True


def run_iscc(dst_file: Path, is_update: bool):
    cmd = [
        str(ISCC_EXE),
        str(ISS_SCRIPT_FILE),
        f'/DAppVersion={SHARLY_CHESS_VERSION}',
        f'/DIsUpdate={int(is_update)}',
    ]
    logger.info('Running command [%s]...', ' '.join(cmd))
    process = subprocess.run(cmd, capture_output=True, text=True)
    logger.info('Command returned [%d].', process.returncode)
    logger.debug(process.stdout)
    if process.returncode != 0:
        logger.warning(process.stderr)
        logger.error('Inno Setup Compiler failed.')
        return False
    if not dst_file.exists():
        logger.error(f'File [{dst_file}] not found.')
        return False
    logger.info(f'File [{dst_file}] successfully generated.')
    return True


if __name__ == '__main__':
    if not check_available():
        sys.exit(1)
    logger.info('Generating Setup file...')
    if not run_iscc(SETUP_EXE, is_update=False):
        sys.exit(1)
    logger.info('Generating Updater file...')
    if not run_iscc(UPDATER_EXE, is_update=True):
        sys.exit(1)
    sys.exit(0)
