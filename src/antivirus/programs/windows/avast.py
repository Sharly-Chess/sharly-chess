import json
from logging import Logger
from pathlib import Path

from antivirus.programs.windows import WindowsAntivirus
from antivirus.uac import UACWrapper
from common import DEVEL_ENV
from common.logger import get_logger
from common.tool_installer import UACInstaller

logger: Logger = get_logger()


class Avast(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            'Avast',
            [
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

    def run(
        self,
        folder: Path,
    ) -> None:
        # There is no way like with Windows Defender to know if the Sharly Chess folder
        # already belongs to the Avast exclusions. So the best we can do is always calling
        # UAC and marking the folder as excluded not to do it twice (if the user removes
        # the exclusion we assume (s)he knows what (s)he does).
        marker_file: Path = self.tmp_dir / f'{self.name}.json'
        if not folder.is_absolute():
            folder = folder.resolve()
        if marker_file.is_file():
            with open(marker_file, 'r', encoding='utf-8') as file:
                marked_folder: str = json.load(file)
                if marked_folder == str(folder):
                    logger.debug(
                        'Folder [%s] has already been add to the Avast exclusions.',
                        folder,
                    )
                    return
        if UACInstaller().is_installed:
            logger.info(
                f'Calling Sharly Chess UAC to add folder [{folder}] to the Avast exclusions...'
            )
            UACWrapper().avast_exclude_sharly_chess_folder(folder)
        elif DEVEL_ENV:
            logger.info(
                'Sharly Chess UAC not installed yet, can not add Sharly Chess folder to the Avast exclusions.'
            )
