"""Unit tests for the event tags.

The tag registry is global to the installation (config database) and events
reference it by id (`info`.`tag_ids`), so renaming an event keeps its tags.
Ids only mean something locally: they are stripped on import, and an id that
no longer resolves is ignored rather than displayed.
"""

import pytest

from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredTag
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils


EVENT_ID = 'test-event-tags'


@pytest.fixture
def tag_ids():
    """Two tags in the global registry, removed again afterwards."""
    with ConfigDatabase(True) as database:
        ids = [
            database.add_stored_tag(StoredTag(id=None, name='Youth', color='#112233')),
            database.add_stored_tag(
                StoredTag(id=None, name='Regional', color='#EEDDCC')
            ),
        ]
    SharlyChessConfig().load_and_set_env()
    yield ids
    with ConfigDatabase(True) as database:
        for tag_id in ids:
            database.delete_stored_tag(tag_id)
    SharlyChessConfig().load_and_set_env()


@pytest.fixture
def event(tag_ids):
    """An event carrying both tags."""
    TestUtils.create_event(EVENT_ID)
    with EventDatabase(EVENT_ID, write=True) as database:
        stored_event = database.load_stored_event()
        stored_event.tag_ids = list(tag_ids)
        database.update_stored_event(stored_event)
    yield EVENT_ID
    # Drop the file rather than EventDatabase.delete(), which archives the
    # event and expects it to have been loaded through the EventLoader.
    EventLoader._valid_event_ids.discard(EVENT_ID)
    EventLoader._invalid_uniq_ids.discard(EVENT_ID)
    EventDatabase(EVENT_ID).file.unlink(missing_ok=True)


@pytest.mark.unit
class TestEventTags:
    def test_tags_are_stored_on_the_event(self, event, tag_ids):
        with EventDatabase(event) as database:
            assert database.load_stored_event().tag_ids == tag_ids

    def test_metadata_carries_the_tags(self, event, tag_ids):
        # The event lists are built from the metadata alone, so the tags have
        # to survive the lightweight load.
        metadata = EventLoader.load_event_metadata(event)
        assert metadata.tag_ids == tag_ids
        assert [tag.name for tag in metadata.tags] == ['Regional', 'Youth']

    def test_tags_are_resolved_and_sorted_by_name(self, event):
        tags = EventLoader().load_event(event).tags
        assert [(tag.name, tag.color) for tag in tags] == [
            ('Regional', '#EEDDCC'),
            ('Youth', '#112233'),
        ]

    def test_renaming_the_event_keeps_the_tags(self, event, tag_ids):
        with EventDatabase(event, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.name = 'Renamed'
            database.update_stored_event(stored_event)
        with EventDatabase(event) as database:
            assert database.load_stored_event().tag_ids == tag_ids

    def test_unknown_tag_ids_are_ignored(self, event, tag_ids):
        with EventDatabase(event, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.tag_ids = [*tag_ids, 999999]
            database.update_stored_event(stored_event)
        event_ = EventLoader().load_event(event)
        # The dangling id is kept in storage but never surfaces as a tag.
        assert event_.tag_ids == [*tag_ids, 999999]
        assert [tag.name for tag in event_.tags] == ['Regional', 'Youth']

    def test_deleting_a_tag_only_hides_it(self, event, tag_ids):
        with ConfigDatabase(True) as database:
            database.delete_stored_tag(tag_ids[0])
        SharlyChessConfig().load_and_set_env()
        assert [tag.name for tag in EventLoader().load_event(event).tags] == [
            'Regional'
        ]

    def test_tags_are_dropped_on_import(self, event):
        with EventDatabase(event, write=True) as database:
            database.delete_all_tags()
        with EventDatabase(event) as database:
            assert database.load_stored_event().tag_ids == []

    def test_updating_a_tag_keeps_the_events_pointing_at_it(self, event, tag_ids):
        with ConfigDatabase(True) as database:
            database.update_stored_tag(
                StoredTag(id=tag_ids[0], name='Junior', color='#010203')
            )
        SharlyChessConfig().load_and_set_env()
        tags = EventLoader().load_event(event).tags
        assert [(tag.name, tag.color) for tag in tags] == [
            ('Junior', '#010203'),
            ('Regional', '#EEDDCC'),
        ]
