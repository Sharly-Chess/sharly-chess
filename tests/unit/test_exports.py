from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.tie_breaks import TieBreakManager
from data.tournament import Tournament
from plugins.chess_results.chess_results_mappers import ChessResultsTieBreak
from tests.test_config import TestUtils


EVENT_ID = 'test-tournament-exporters-event'
TOURNAMENT_ID = 'tournament-test-exporters'


@pytest.mark.unit
class TournamentExporterTestCase(TestCase):
    event: Event
    tournament: Tournament

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')
        self.event = EventLoader().load_event(EVENT_ID)
        self.tournament = self.event.tournaments_by_uniq_id[TOURNAMENT_ID]

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    # -------------------------------------------------------------------------
    # Chess-Results
    # -------------------------------------------------------------------------

    def test_chess_results_all_tie_breaks_implemented(self):
        for tie_break in TieBreakManager(self.event).objects():
            try:
                ChessResultsTieBreak.from_tie_break(self.tournament, tie_break)
            except NotImplementedError:
                self.fail(f'Tie-break [{tie_break.id}] not handled.')
