"""School code column of the player import.

A team event imports players at the event level, with no tournament;
the school code still places each player in the event's school.
"""

import contextlib
from unittest import TestCase

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredPlayer
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_entity import FraSchoolCodeDatasheetColumn
from plugins.fra_schools.utils import FRASchool, FRASchoolsUtils
from tests.test_config import TestUtils
from utils.enum import EventType

EVENT_ID = 'test-fra-schools-import'
SCHOOL_CODE = '0291869Z'


@pytest.mark.unit
class FraSchoolCodeImportTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})

    def tearDown(self) -> None:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        TestUtils.delete_event(EVENT_ID)

    def test_school_code_sets_the_school_without_a_tournament(self):
        event = EventLoader().load_event(EVENT_ID)
        school_id = FRASchoolsUtils.add_event_school(
            event, FRASchool(code=SCHOOL_CODE, name='LA CROIX ROUGE'), save=False
        )
        stored_player = StoredPlayer(id=None)
        FraSchoolCodeDatasheetColumn().augment_stored_player_with_tournament(
            event, None, stored_player, SCHOOL_CODE
        )
        assert stored_player.plugin_data[PLUGIN_NAME]['fra_school_id'] == school_id
