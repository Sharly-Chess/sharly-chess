from pathlib import Path

from common.logger import (
    get_logger,
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
)
from data.pairings.engines import BbpPairings
from utils import StaticUtils

logger = get_logger()


class BbpPairingsGenerator(BbpPairings):
    def generate_tournament(
        self,
        trf_file_path: Path,
        cache: bool = False,
    ) -> bool:
        """Generates a random tournament and dumps to file
        in TRFX format, returns True on success, False otherwise."""
        try:
            if cache:
                if trf_file_path.exists():
                    print_interactive_info(
                        f'TRF file {trf_file_path.name} read from cache.'
                    )
                    return True
            else:
                trf_file_path.unlink(missing_ok=True)
            print_interactive_info(
                f'Generating random tournament to TRF file {trf_file_path.name}...'
            )
            trf_file_path.parent.mkdir(parents=True, exist_ok=True)
            result = StaticUtils.run_process(
                [
                    str(self.executable_path),
                    # dutch pairing
                    '--dutch',
                    # generate
                    '-g',
                    # output file
                    '-o',
                    str(trf_file_path),
                ],
                capture_output=True,
                encoding='utf-8',
            )
            if result.returncode:
                print_interactive_error(
                    f'BbpPairings random tournament generator failed with status {result.returncode}.'
                )
                print_interactive_error(f'stdout: {result.stdout}')
                print_interactive_error(f'stderr: {result.stderr}')
                return False
            print_interactive_success(
                f'BbpPairings random tournament generator created TRF file {trf_file_path.name}.'
            )
            return True
        except BaseException as be:
            print_interactive_error(f'Exception: {be}')
            trf_file_path.unlink(missing_ok=True)
            raise
