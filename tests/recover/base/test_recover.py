import os
from logging import Logger
from pathlib import Path
from unittest import TestCase

import pytest
from packaging.version import Version

from common import LOG_FILE, EVENTS_FOLDER
from common.logger import get_logger
from common.engine import Engine
from data.event import Event
from data.loader import EventLoader


class _TestEngine(Engine):
    @property
    def log_file_path(self) -> Path:
        return LOG_FILE


logger: Logger = get_logger()


@pytest.mark.recovering
class RecoverTestCase(TestCase):
    """Tests the recovering of 2.4.0 events."""

    def test_recover(self):
        # Note(pascalaubry): engines recover previous releases data
        # with method _recover_previous_version() by looking
        # for previous instances in folder ..
        logger.info('Loading test engine...')
        test_engine = _TestEngine()
        version: Version = Version('2.4.0')
        dir_name: str = f'papi-web-{version}'
        cwd: str = os.getcwd()
        os.chdir(Path(__file__).parent)
        events_folder: Path = Path('..') / dir_name / EVENTS_FOLDER
        files: list[Path] = [file for file in events_folder.glob('*.db')]
        logger.info('Recovering version [%s]...', version)
        test_engine._recover_previous_version(
            version,
            dir_name,
            files,
        )
        for file in files:
            event_uniq_id: str = file.stem
            logger.info('Loading event [%s]]...', event_uniq_id)
            event: Event = EventLoader().load_event(event_uniq_id)
            logger.info('Tournaments: %d', len(event.tournaments_by_id))
            logger.info('Players: %d', len(event.players_by_id))
        logger.info('Done.')
        os.chdir(cwd)
