"""Which players-tab columns an event enables.

The decision is the event's, not a tournament's: teams and their players
exist before any tournament does, so an event with no tournament yet must
still offer the team column.
"""

from unittest import TestCase

import pytest

from data.columns.handlers import PlayersTabColumnHandler
from data.loader import EventLoader
from tests.test_config import TestUtils
from utils.enum import EventType

TEAM_EVENT_ID = 'test-players-tab-columns-team'
INDIVIDUAL_EVENT_ID = 'test-players-tab-columns-individual'


def _enabled_column_ids(event_id: str) -> set[str]:
    try:
        EventLoader.unload_event(event_id)
    except KeyError:
        pass
    event = EventLoader().load_event(event_id)
    handler = PlayersTabColumnHandler(event)
    tournaments = list(event.tournaments)
    return {
        column.id
        for column in handler.columns
        if column.is_enabled_for_event(event, tournaments)
    }


@pytest.mark.unit
class PlayersTabColumnsTestCase(TestCase):
    def tearDown(self) -> None:
        for event_id in (TEAM_EVENT_ID, INDIVIDUAL_EVENT_ID):
            try:
                TestUtils.delete_event(event_id)
            except Exception:
                pass

    def test_team_column_without_any_tournament(self):
        TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
        assert 'team' in _enabled_column_ids(TEAM_EVENT_ID)

    def test_team_column_with_a_tournament(self):
        TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            TEAM_EVENT_ID,
            'team-tournament',
            overrides={'pairing': 'TEAM_SWISS_STANDARD', 'team_player_count': 1},
        )
        assert 'team' in _enabled_column_ids(TEAM_EVENT_ID)

    def test_no_team_column_in_an_individual_event(self):
        TestUtils.create_event(INDIVIDUAL_EVENT_ID)
        assert 'team' not in _enabled_column_ids(INDIVIDUAL_EVENT_ID)

    def test_check_in_column_follows_the_event_not_a_tournament(self):
        TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
        assert 'check_in' not in _enabled_column_ids(TEAM_EVENT_ID)

    def test_check_in_column_is_offered_in_an_individual_event(self):
        TestUtils.create_event(INDIVIDUAL_EVENT_ID)
        assert 'check_in' in _enabled_column_ids(INDIVIDUAL_EVENT_ID)
