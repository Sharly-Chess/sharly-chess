from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class McAfee(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            'McAfee',
            [
                'mcshield.exe',
                'mcupdate.exe',
            ],
        )
