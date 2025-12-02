from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class IDefenseLab(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            'iDefense Lab',
            [
                'api_log.dll',
                'dir_watch.dll',
            ],
        )
