from abc import ABC
from logging import Logger
from pathlib import Path

from common import TMP_DIR
from common.logger import get_logger

logger: Logger = get_logger()


class Antivirus(ABC):
    def __init__(
        self,
        name: str,
        signatures: list[str],
    ):
        self.name = name
        self.signatures: list[str] = signatures
        self.tmp_dir = TMP_DIR / 'antivirus'
        self.tmp_dir.mkdir(exist_ok=True)

    def run(
        self,
        folder: Path,
    ) -> None:
        """Executes an action to prevent the antivirus from interfering with the program's execution."""
        pass
