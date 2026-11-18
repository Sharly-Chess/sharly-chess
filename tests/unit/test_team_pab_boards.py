"""The boards of a team given the pairing-allocated bye: the colour pattern
seats its players on both sides, and every board reads as a bye won by the
player present."""

import contextlib
from unittest import TestCase

import pytest

from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType

EVENT_ID = 'test-team-pab-boards'
TOURNAMENT_NAME = 'swiss'
N = 4
TEAMS = 5


@pytest.mark.unit
class TeamPabBoardsTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        stored_tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 3,
                'team_player_count': N,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        )
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            for seed in range(1, TEAMS + 1):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                for index in range(N):
                    player_id = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{index}',
                            team_id=team_id,
                            team_index=index,
                            check_in=True,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_id,
                            pairing_number=index + 1,
                        )
                    )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load(self) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_every_board_of_the_team_given_the_bye_reads_as_its_bye(self) -> None:
        tournament = self._load()
        self.assertEqual(
            tournament.pairing_variation.engine.generate_pairings(tournament, 1), ''
        )
        tournament = self._load()
        bye_match = next(
            team_board
            for team_board in tournament.get_round_team_boards(1)
            if team_board.stored_team_board.team_b_id is None
        )
        boards = bye_match.boards
        self.assertEqual(len(boards), N)
        on_white = [b for b in boards if b.optional_white_tournament_player]
        on_black = [b for b in boards if b.black_tournament_player]
        self.assertTrue(on_white)
        self.assertTrue(on_black)
        self.assertTrue(all(board.is_pab_board for board in boards))
        self.assertEqual({board.result_str for board in on_white}, {'1-F'})
        self.assertEqual({board.result_str for board in on_black}, {'F-1'})
        played = [
            board
            for team_board in tournament.get_round_team_boards(1)
            if team_board is not bye_match
            for board in team_board.boards
        ]
        self.assertFalse(any(board.is_pab_board for board in played))
