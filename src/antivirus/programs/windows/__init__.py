from logging import Logger

from antivirus.programs.antivirus import Antivirus
from common.logger import get_logger

logger: Logger = get_logger()


class WindowsAntivirus(Antivirus):
    def __init__(
        self,
        name: str,
        doc_url: str,
        signatures: list[str],
    ):
        super().__init__(name, doc_url, signatures)
