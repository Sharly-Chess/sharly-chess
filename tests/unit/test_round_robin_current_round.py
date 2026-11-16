from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-round-robin-current-round-event'
TOURNAMENT_ID = 'test-round-robin-current-round-tournament'


@pytest.mark.unit
class RoundRobinCurrentRoundTestCase(TestCase):
    """The round in play of a round-robin follows the results entered when no
    round is published, so a tournament played to the end without screens or
    online services is finished and ranked."""

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='manual-koya')
        self._load().set_published_round(0)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load(self) -> Tournament:
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def test_a_tournament_played_to_the_end_unpublished_is_finished(self):
        tournament = self._load()
        self.assertEqual(tournament.current_round, tournament.rounds)
        self.assertTrue(tournament.finished)
        self.assertEqual(tournament.max_ranking_round, tournament.rounds)

    def test_the_round_in_play_is_the_last_one_played(self):
        tournament = self._load()
        for round_ in (6, 7):
            for board in tournament.get_round_boards(round_):
                if board.black_tournament_player is not None:
                    tournament.add_result(board, Result.NO_RESULT)
        tournament = self._load()
        self.assertEqual(tournament.current_round, 5)
        self.assertFalse(tournament.finished)
        self.assertEqual(tournament.max_ranking_round, 5)

    def test_a_published_round_ahead_of_the_results_is_in_play(self):
        tournament = self._load()
        for round_ in (6, 7):
            for board in tournament.get_round_boards(round_):
                if board.black_tournament_player is not None:
                    tournament.add_result(board, Result.NO_RESULT)
        tournament.set_published_round(6)
        tournament = self._load()
        self.assertEqual(tournament.current_round, 6)
        self.assertTrue(tournament.playing)
        self.assertEqual(tournament.max_ranking_round, 5)
