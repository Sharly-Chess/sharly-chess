import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from common import EVENTS_DIR
from common.exception import DatabaseInaccessibleException
from data import loader
from data.loader import INACCESSIBLE_EVENT_RETRY_DELAY, EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import Extension

INACCESSIBLE_ID = 'test-loader-inaccessible'
IMPORTED_ID = 'test-loader-imported'


@pytest.fixture(autouse=True)
def remove_the_events_afterwards():
    yield
    for uniq_id in (INACCESSIBLE_ID, IMPORTED_ID):
        EventLoader.unload_event(uniq_id)
        EventDatabase.event_database_path(uniq_id).unlink(missing_ok=True)


@pytest.mark.unit
class TestInaccessibleEvents:
    def test_a_scan_tries_an_inaccessible_event_again_only_after_a_delay(self):
        """Each try at a file the system refuses takes SQLite about a second
        and a half on Windows, and a page scans the events several times."""
        TestUtils.create_event(INACCESSIBLE_ID)
        check_event_database = EventLoader.check_event_database
        tried: list[str] = []

        def refuse(uniq_id: str):
            if uniq_id == INACCESSIBLE_ID:
                tried.append(uniq_id)
                raise DatabaseInaccessibleException('refused')
            return check_event_database(uniq_id)

        now = 1000.0
        with (
            patch.object(EventLoader, 'check_event_database', side_effect=refuse),
            patch.object(loader, 'monotonic', side_effect=lambda: now),
        ):
            EventLoader.unload_event(INACCESSIBLE_ID)
            EventLoader.load_event_ids()
            assert len(tried) == 1
            assert INACCESSIBLE_ID in EventLoader.damaged_event_ids()

            now += INACCESSIBLE_EVENT_RETRY_DELAY
            EventLoader.load_event_ids()
            assert len(tried) == 2

    def test_an_event_asked_for_is_tried_again_straight_away(self):
        TestUtils.create_event(INACCESSIBLE_ID)
        check_event_database = EventLoader.check_event_database
        refused = True

        def refuse_once(uniq_id: str):
            if uniq_id == INACCESSIBLE_ID and refused:
                raise DatabaseInaccessibleException('refused')
            return check_event_database(uniq_id)

        with patch.object(EventLoader, 'check_event_database', side_effect=refuse_once):
            EventLoader.unload_event(INACCESSIBLE_ID)
            assert INACCESSIBLE_ID in EventLoader.damaged_event_ids()
            refused = False
            assert INACCESSIBLE_ID in EventLoader.load_event_ids(INACCESSIBLE_ID)


@pytest.mark.unit
class TestImportEvent:
    def test_the_uploaded_file_is_copied_into_the_events_and_removed(self):
        TestUtils.create_event(IMPORTED_ID)
        upload_dir = Path(tempfile.mkdtemp())
        upload = upload_dir / f'{IMPORTED_ID}.{Extension.EVENT_DB}'
        shutil.copyfile(EventDatabase.event_database_path(IMPORTED_ID), upload)
        EventLoader.unload_event(IMPORTED_ID)
        EventDatabase.event_database_path(IMPORTED_ID).unlink()
        try:
            uniq_id = EventLoader().import_event(upload)

            assert uniq_id == IMPORTED_ID
            assert not upload.exists()
            assert (EVENTS_DIR / f'{IMPORTED_ID}.{Extension.EVENT_DB}').is_file()
            assert EventLoader.load_event_metadata(IMPORTED_ID).uniq_id == IMPORTED_ID
        finally:
            shutil.rmtree(upload_dir, ignore_errors=True)
