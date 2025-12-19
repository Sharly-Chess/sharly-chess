import re
from logging import Logger
from pathlib import Path

from antivirus.programs.windows import WindowsAntivirus, WinRegistry
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

    @staticmethod
    def _get_exclusions() -> list[str]:
        """Returns all the Avast exclusions."""
        exclusions: list[str] = []
        value: str = WinRegistry.get_hklm_value(
            r'SOFTWARE\Avast Software\Avast\properties\exclusions\Global',
            'ExcludeFiles',
        )
        if value:
            for string_part in value.split(';'):
                if matches := re.match(r'^"([^"]+)"$', string_part):
                    exclusions.append(matches.group(1))
                else:
                    logger.debug(f'Unrecognised string [{string_part}]')
        if exclusions:
            logger.debug('Avast exclusions are:')
            for exclusion in exclusions:
                logger.debug(f'- {exclusion}')
        else:
            logger.debug('No Avast exclusions found.')
        return exclusions

    def run(
        self,
        folder: Path,
    ) -> None:
        if not folder.is_absolute():
            folder = folder.resolve()
        lower_folder: str = str(folder).lower()
        for exclusion in self._get_exclusions():
            if lower_folder.startswith(exclusion):
                logger.info(
                    f'Sharly Chess folder [{folder}] belongs to the Avast exclusions.'
                )
                return
        super().run(folder)
