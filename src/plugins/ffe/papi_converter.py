from pathlib import Path
import subprocess

from common.exception import SharlyChessException
from common.tool_installer import PapiConverterInstaller


class PapiConverter:
    """Wrapper on the Papi converter
    (see https://github.com/Sharly-Chess/papi-converter)"""

    @property
    def executable_path(self) -> Path:
        return PapiConverterInstaller().executable_path

    def convert_player_database(self, source_file: Path, target_file: Path) -> bool:
        """Converts the .mdb player database to an SQLLite database."""
        result = subprocess.run(
            [
                self.executable_path,
                '--playerdb',
                source_file,
                target_file,
            ],
            capture_output=True,
            encoding='utf-8',
        )
        if not target_file.exists():
            raise SharlyChessException(
                f'Player database conversion error.'
                f'PapiConverter failed with status {result.returncode}.\n'
                f'stdout: {result.stdout}\nstderr: {result.stderr}'
            )
