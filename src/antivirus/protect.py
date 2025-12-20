import os
import sys
from logging import Logger
from pathlib import Path

from antivirus.programs.antivirus import Antivirus
from common.logger import get_logger

logger: Logger = get_logger()


def protect_from_antivirus_programs(
    detected_antivirus_programs: list[Antivirus],
    folder: Path,
):
    """Protect Sharly Chess from the given running antivirus programs (adds exclusions for the given folder when possible)."""
    if os.getenv('TEST_ENV') == 'true' or Path(sys.argv[0]).stem == 'pytest':
        return
    for detected_antivirus_program in detected_antivirus_programs:
        logger.debug('Running action for [%s]...', detected_antivirus_program.name)
        detected_antivirus_program.run(folder or Path())
