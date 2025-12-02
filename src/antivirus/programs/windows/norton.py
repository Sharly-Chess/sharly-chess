from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class Norton(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            'Norton',
            [
                'ccSvcHst.exe',
                'norton.exe',
            ],
        )
