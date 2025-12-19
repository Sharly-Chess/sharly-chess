from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class Norton(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Norton',
            doc_url='https://support.norton.com/sp/en/us/home/current/solutions/v20240108162522348',
            signatures=[
                'ccSvcHst.exe',
                'norton.exe',
            ],
        )
