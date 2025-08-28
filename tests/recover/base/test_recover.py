import os
from logging import Logger
from pathlib import Path
from unittest import TestCase

import pytest
from packaging.version import Version

from common import LOG_FILE
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
        version: Version = Version('2.4.0')
        dir_name: str = f'papi-web-{version}'
        cwd: str = os.getcwd()
        os.chdir(Path(__file__).parent)
        files: list[Path] = [file for file in (Path('../..') / dir_name).glob('*.db')]
        logger.info('Loading test engine...')
        test_engine = _TestEngine()
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
            logger.info('Players: %d', len(event.tournaments_by_id))
        logger.info('Done.')
        os.chdir(cwd)
