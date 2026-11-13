"""Unit tests for the space taken by the images of the image screens.

An uploaded image is stored in the event, so the file is rebuilt whenever an
image is added, replaced or removed: SQLite would otherwise keep the pages of
the old image inside the file.
"""

import base64
import os
import sqlite3

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from tests.test_config import TestUtils


EVENT_ID = 'test-screen-image-space'


def _image(size: int) -> str:
    return 'data:image/jpeg;base64,' + base64.b64encode(os.urandom(size)).decode()


def _free_pages() -> int:
    connection = sqlite3.connect(EventDatabase(EVENT_ID).file)
    try:
        return connection.execute('PRAGMA freelist_count').fetchone()[0]
    finally:
        connection.close()


def _add_screen(background_image: str | None) -> StoredScreen:
    with EventDatabase(EVENT_ID, write=True) as database:
        return database.add_stored_screen(
            StoredScreen(
                id=None,
                uniq_id='image-screen',
                name=None,
                type='image',
                columns=None,
                font_size=None,
                menu_text=None,
                timer_id=None,
                background_image=background_image,
            )
        )


@pytest.fixture(autouse=True)
def event():
    TestUtils.create_event(EVENT_ID)
    yield
    # Drop the file rather than EventDatabase.delete(), which archives the
    # event and expects it to have been loaded through the EventLoader.
    EventLoader._valid_event_ids.discard(EVENT_ID)
    EventLoader._invalid_uniq_ids.discard(EVENT_ID)
    EventDatabase(EVENT_ID).file.unlink(missing_ok=True)


@pytest.mark.unit
class TestScreenImageSpace:
    def test_replacing_an_image_frees_its_space(self):
        stored_screen = _add_screen(_image(1_000_000))
        stored_screen.background_image = _image(10_000)
        with EventDatabase(EVENT_ID, write=True) as database:
            database.update_stored_screen(stored_screen)
        assert _free_pages() == 0
        assert EventDatabase(EVENT_ID).file.stat().st_size < 1_000_000

    def test_removing_an_image_frees_its_space(self):
        stored_screen = _add_screen(_image(1_000_000))
        stored_screen.background_image = None
        with EventDatabase(EVENT_ID, write=True) as database:
            database.update_stored_screen(stored_screen)
        assert _free_pages() == 0

    def test_deleting_an_image_screen_frees_its_space(self):
        stored_screen = _add_screen(_image(1_000_000))
        assert stored_screen.id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_stored_screen(stored_screen.id)
        assert _free_pages() == 0
        assert EventDatabase(EVENT_ID).file.stat().st_size < 1_000_000

    def test_changing_the_type_of_an_image_screen_frees_its_space(self):
        stored_screen = _add_screen(_image(1_000_000))
        stored_screen.type = 'boards'
        with EventDatabase(EVENT_ID, write=True) as database:
            database.update_stored_screen(stored_screen)
        assert _free_pages() == 0

    def test_adding_an_image_frees_the_space_left_by_earlier_changes(self):
        with EventDatabase(EVENT_ID, write=True) as database:
            database.execute('CREATE TABLE `filler` (`data` BLOB)')
            database.execute('INSERT INTO `filler` VALUES (?)', (os.urandom(500_000),))
        with EventDatabase(EVENT_ID, write=True) as database:
            database.execute('DROP TABLE `filler`')
        assert _free_pages() > 0
        _add_screen(_image(10_000))
        assert _free_pages() == 0
