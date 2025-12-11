from logging import Logger
from pathlib import Path

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class ESET(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            'ESET',
            [
                'Efwd.exe',
                'ekrn.exe',
                'eServiceHost.exe',
            ],
        )

    def run(
        self,
        folder: Path,
    ) -> None:
        if not folder.is_absolute():
            folder = folder.resolve()
        logger.warning(
            'Sharly Chess has no way to know the exclusions set in ESET, so you should (if not already done) add '
            'an ESET exclusion for the following folder to prevent you from arbitrary ESET file deletions:\n'
            f'- [{folder}]\n'
            'Please refer to https://sharly-chess.com/antivirus/eset to learn how to add a path exception in ESET.\n'
        )
