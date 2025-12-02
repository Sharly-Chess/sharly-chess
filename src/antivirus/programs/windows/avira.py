from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class Avira(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            'Avira',
            [
                'avguard.exe',
                'avscan.exe',
            ],
        )
