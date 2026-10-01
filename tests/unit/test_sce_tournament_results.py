"""The tournament results payload uploaded to the SCE platform."""

from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from plugins.sce.sce_tournament_results_builder import build_tournament_results
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-sce-tournament-results-event'
TOURNAMENT_ID = 'test-sce-tournament-results-tournament'


@pytest.mark.unit
class SCETournamentResultsTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID, TOURNAMENT_ID, json_file='median-buchholz-byes'
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def test_requested_byes_are_sent_as_unpaired_rows(self) -> None:
        self._event: Event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_ID]
        payload = build_tournament_results(tournament, 'sce-event', 'sce-tournament')

        expected = {
            (round_, player.pairing_number, pairing.result.value)
            for player in tournament.tournament_players
            for round_, pairing in player.pairings.items()
            if pairing.board is None and pairing.result != Result.NO_RESULT
        }
        self.assertTrue(expected)
        self.assertEqual(
            expected,
            {
                (
                    pairing['round'],
                    pairing['whitePairingNumber'],
                    pairing['whiteResult'],
                )
                for pairing in payload['pairings']
                if pairing['blackPairingNumber'] == -2
            },
        )
