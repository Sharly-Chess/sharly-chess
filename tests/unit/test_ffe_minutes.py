"""The FFE minutes (T2) open with what the tournaments logged for their TRF."""

from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.pibes import Pibe, PibeType
from data.tournament import Tournament
from plugins.ffe.print_documents.ffe_types import FFET2Type
from tests.test_config import TestUtils

EVENT_ID = 'test-ffe-minutes-event'
TOURNAMENT_ID = 'test-ffe-minutes-tournament'


@pytest.mark.unit
class FFEMinutesTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _tournament(self) -> Tournament:
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def test_nothing_to_report(self):
        self.assertEqual(
            FFET2Type.report_text_for([self._tournament()]), 'Rien à signaler.'
        )

    def test_the_logged_events_are_reported(self):
        self._tournament().log_pibe(Pibe(PibeType.CORRECTION, 4, '6-7: 1-0 => 0-1'))

        text = FFET2Type.report_text_for([self._tournament()])

        players = self._tournament().tournament_players_by_pairing_number
        self.assertIn(f'{TOURNAMENT_ID} :', text)
        self.assertIn(
            f'- Ronde 4 : Résultat de {players[6].full_name} – '
            f'{players[7].full_name} corrigé de 1-0 en 0-1.',
            text,
        )
