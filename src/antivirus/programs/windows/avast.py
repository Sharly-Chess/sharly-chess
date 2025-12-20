from logging import Logger

from antivirus.programs.windows import WindowsAntivirus
from common.logger import get_logger

logger: Logger = get_logger()


class Avast(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Avast',
            doc_url='https://support.avast.com/en-us/article/antivirus-scan-exclusions',
            signatures=[
                'snxhk.dll',
                'sf2.dll',
                'AvastUI.exe',
                'aswToolsSvc.exe',
                'aswEngSrv.exe',
                'afwServ.exe',
                'wsc_proxy.exe',
                'AvastSvc.exe',
                'aswidsagent.exe',
            ],
        )
