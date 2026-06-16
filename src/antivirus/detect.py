import os
import sys
from logging import Logger
from pathlib import Path

from antivirus.programs.antivirus import Antivirus
from common.logger import get_logger

logger: Logger = get_logger()


def detect_antivirus_programs() -> list[Antivirus]:
    """Return known antivirus programs running on the server."""
    if os.getenv('TEST_ENV') == 'true' or Path(sys.argv[0]).stem == 'pytest':
        return []
    match sys.platform:
        case 'win32':
            import psutil
            from antivirus.programs.windows.avast import Avast
            from antivirus.programs.windows.avg import AVG
            from antivirus.programs.windows.avira import Avira
            from antivirus.programs.windows.eset import ESET
            from antivirus.programs.windows.f_secure import FSecure
            from antivirus.programs.windows.kaspersky import Kaspersky
            from antivirus.programs.windows.norton import Norton
            from antivirus.programs.windows.trend_micro import TrendMicro
            from antivirus.programs.windows.windows_defender import WindowsDefender

            detected_antivirus_programs: list[Antivirus] = []
            try:
                logger.debug('Analysing running processes...')
                process_names: list[str] = [
                    process.info['name'].lower()
                    for process in psutil.process_iter(attrs=['name'])
                ]
                for avs in [
                    Avast(),
                    Avira(),
                    AVG(),
                    ESET(),
                    FSecure(),
                    Kaspersky(),
                    Norton(),
                    TrendMicro(),
                    WindowsDefender(),
                ]:
                    for signature in avs.signatures:
                        if signature.lower() in process_names:
                            logger.debug(
                                'Process [%s] identifies antivirus [%s].',
                                signature,
                                avs.name,
                            )
                            detected_antivirus_programs.append(avs)
                            break
            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ) as e:
                logger.warning('Could not detect antivirus programs: %s', e)
            if detected_antivirus_programs:
                logger.debug('The following antivirus programs have been detected:')
                for detected_antivirus_program in detected_antivirus_programs:
                    logger.debug('- %s', detected_antivirus_program.name)
            else:
                logger.debug('No antivirus program has been detected.')
            return detected_antivirus_programs
        case _:
            logger.debug('No antivirus detection for platform [%s].', sys.platform)
    return []
