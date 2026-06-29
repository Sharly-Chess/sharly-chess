from logging import Logger
from pathlib import Path
from unittest import TestCase

import pytest
from packaging.version import Version, InvalidVersion

from common.logger import get_logger
from common.version_updater import VersionUpdater
from data.event import Event
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from utils.enum import Extension

logger: Logger = get_logger()


@pytest.mark.release_only
class RecoverTestCase(TestCase):
    """Tests the recovering of 2.4.0 events."""

    def test_recover(self):
        # Note(pascalaubry): engines recover previous releases data
        # by looking for previous instances in folder ..
        logger.info('Loading test engine...')
        for version_dir in Path(__file__).parent.glob('*'):
            if not version_dir.is_dir():
                continue
            try:
                version: Version = Version(version_dir.name)
            except InvalidVersion:
                logger.debug('Invalid version [%s]...', version_dir.name)
                continue
            events_folder: Path = version_dir / 'events'
            files = list(events_folder.glob(f'*.{Extension.EVENT_DB}')) + list(
                events_folder.glob(f'*.{Extension.LEGACY_EVENT_DB}')
            )
            logger.info('Recovering version [%s]...', version)
            VersionUpdater.recover_version_pre_v5(
                version,
                version_dir,
                files,
            )
            for file in files:
                event_uniq_id: str = file.stem
                logger.info('Loading event [%s]...', event_uniq_id)
                event: Event = EventLoader().load_event(event_uniq_id)
                logger.info('Tournaments: %d', len(event.tournaments_by_id))
                assert event.tournaments_by_id, (
                    f'No tournaments recovered from event [{event_uniq_id}] of version {version}.'
                )
                logger.info('Players: %d', len(event.players_by_id))
                assert event.players_by_id, (
                    f'No players recovered from event [{event_uniq_id}] of version {version}.'
                )
                logger.info('Deleting database [%s]...', event_uniq_id)
                EventDatabase(event_uniq_id).delete()
        logger.info('Done.')
