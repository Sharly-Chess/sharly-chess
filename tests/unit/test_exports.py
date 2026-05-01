from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.tie_breaks import TieBreakManager, TieBreak
from data.tie_breaks.tie_breaks import StandardBuchholzTieBreak, WinsTieBreak
from data.tournament import Tournament
from plugins.chess_results.chess_results_mappers import ChessResultsTieBreak
from plugins.ffe.ffe_tie_breaks import PapiPerformanceTieBreak
from plugins.ffe.papi_converter import PapiConverter
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
        self.tournament = self.event.tournaments_by_name[TOURNAMENT_ID]

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

    # -------------------------------------------------------------------------
    # Papi
    # -------------------------------------------------------------------------

    def _set_tie_breaks(self, tie_breaks: list[TieBreak]):
        self.tournament.tie_breaks_by_id = {
            index + 1: tie_break for index, tie_break in enumerate(tie_breaks)
        }

    def test_papi_manual_tie_break_pairing_number(self):
        """Check that the pairing number is added as a tie-break if a spot is available."""
        self._set_tie_breaks([PapiPerformanceTieBreak()])
        papi_data = PapiConverter().tournament_to_papi_data(self.tournament)
        self.assertEqual(papi_data.variables.tiebreak2, 'Manuel')
        expected_fixed_by_player = {
            'ALYX': 1016,
            'BRUNO': 1015,
            'CHARLINE': 1014,
            'DAVID': 1013,
            'HELENE': 1012,
            'FRANCK': 1011,
            'GENEVIEVE': 1010,
            'IRINA': 1009,
            'JESSICA': 1008,
            'LAIS': 1007,
            'MARIA': 1006,
            'NICK': 1005,
            'OPAL': 1004,
            'PAUL': 1003,
            'REINE': 1002,
            'STEPHAN': 1001,
        }
        for player in papi_data.players:
            self.assertIn(player.lastName, expected_fixed_by_player)
            self.assertEqual(
                expected_fixed_by_player[player.lastName], player.fixedBoard
            )

    def test_papi_incompatible_tie_breaks_replaced(self):
        """Check that the rankings replaces the first incompatible tie-break."""
        self._set_tie_breaks(
            [
                WinsTieBreak(),
                StandardBuchholzTieBreak(),
                PapiPerformanceTieBreak(),
            ]
        )
        papi_data = PapiConverter().tournament_to_papi_data(self.tournament)

        self.assertEqual(papi_data.variables.tiebreak1, 'Nombre de Victoires')
        self.assertEqual(papi_data.variables.tiebreak2, 'Manuel')
        self.assertEqual(papi_data.variables.tiebreak3, None)
        expected_fixed_by_player = {
            'BRUNO': 1016,
            'STEPHAN': 1015,
            'CHARLINE': 1014,
            'DAVID': 1013,
            'ALYX': 1012,
            'FRANCK': 1011,
            # Maria / Irina swapped from 03/2026 FIDE tie-breaks dummy update
            # Maria BH -1 --> Forfeit win R4 - 1 * (dummy capped to opponent score 1.5 instead of 2.5)
            'IRINA': 1010,
            'MARIA': 1009,
            'HELENE': 1008,
            'REINE': 1007,
            'NICK': 1006,
            'PAUL': 1005,
            'GENEVIEVE': 1004,
            'OPAL': 1003,
            'JESSICA': 1002,
            'LAIS': 1001,
        }
        for player in papi_data.players:
            self.assertIn(player.lastName, expected_fixed_by_player)
            self.assertEqual(
                expected_fixed_by_player[player.lastName], player.fixedBoard
            )
