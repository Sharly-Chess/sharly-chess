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
        doc_url: str,
        signatures: list[str],
    ):
        self.name: str = name
        self.doc_url: str = doc_url
        self.signatures: list[str] = signatures
        self.tmp_dir = TMP_DIR / 'antivirus'
        self.tmp_dir.mkdir(exist_ok=True)

    def run(
        self,
        folder: Path,
    ) -> None:
        """Executes an action to prevent the antivirus from interfering with the program's execution.
        By default, nothing is done but inviting the user to set an exclusion for the Sharly Chess folder."""
        if not folder.is_absolute():
            folder = folder.resolve()
        logger.warning(
            f'Antivirus {self.name} has been detected.'
            f'Sharly Chess has no way to know the exclusions set in {self.name}.\n'
            f'So you should (if not already done) add an exclusion in {self.name} for the following folder to prevent\n'
            f'you from arbitrary {self.name} file deletions:\n'
            f'- [{folder}]\n'
            f'Please refer to {self.doc_url} to learn how to add a path exception in {self.name}.'
        )
