from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class TrendMicro(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Trend micro',
            doc_url='https://docs.trendmicro.com/en-us/documentation/article/trend-vision-one-config-the-scan-exclusion-lists',
            signatures=[
                'tmbmsrv.exe',
                'tmpfw.exe',
                'ntrtscan.exe',
                'tmlisten.exe',
                'dsagent.exe',
                'tmproxy.exe',
            ],
        )
