"""The result of a team-match board the opposing team left empty.

The present player wins by forfeit, or forfeits too (F-F) when they did
not show up either; no other result can be recorded against an empty seat.
"""

import pytest

from data.board import Board
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from tests.unit.test_team_empty_lineup import EVENT_ID, N, _TeamLineupHarness
from utils.enum import Result


@pytest.mark.unit
class TeamForfeitHoleResultTestCase(_TeamLineupHarness):
    HOLE_SLOT = 1

    def setUp(self) -> None:
        super().setUp()
        lineup: list[int | None] = list(self.player_ids[0])
        lineup[self.HOLE_SLOT] = None
        with EventDatabase(EVENT_ID, write=True) as database:
            self._team(self._load(), 0).set_round_lineup(1, lineup, database)
        self.assertEqual(self._load().generate_round_pairings(1), '')

    def _hole_board(self, tournament: Tournament) -> Board:
        return next(
            board
            for board in tournament.get_round_boards(1)
            if board.team_forfeit_hole_pairing is not None
        )

    @staticmethod
    def _white_result(board: Board, player_result: Result) -> Result:
        """The white-oriented result that records *player_result* for the
        board's present player."""
        if board.optional_white_tournament_player is not None:
            return player_result
        return player_result.opposite_result

    def test_the_present_player_wins_by_forfeit(self) -> None:
        tournament = self._load()
        hole_boards = [
            board
            for board in tournament.get_round_boards(1)
            if board.team_forfeit_hole_pairing is not None
        ]
        self.assertEqual(len(hole_boards), 1)
        pairing = hole_boards[0].team_forfeit_hole_pairing
        assert pairing is not None
        self.assertEqual(pairing.result, Result.FORFEIT_WIN)
        team_board = hole_boards[0].team_board
        assert team_board is not None
        self.assertEqual(sum(team_board.game_points), 1)

    def test_a_full_board_is_not_a_hole(self) -> None:
        tournament = self._load()
        full_boards = [
            board
            for board in tournament.get_round_boards(1)
            if board.optional_white_tournament_player is not None
            and board.black_tournament_player is not None
        ]
        self.assertEqual(len(full_boards), 2 * N - 1)
        for board in full_boards:
            self.assertIsNone(board.team_forfeit_hole_pairing)

    def test_an_absent_present_player_forfeits_too(self) -> None:
        tournament = self._load()
        board = self._hole_board(tournament)
        tournament.add_result(board, self._white_result(board, Result.DOUBLE_FORFEIT))
        tournament = self._load()
        board = self._hole_board(tournament)
        pairing = board.team_forfeit_hole_pairing
        assert pairing is not None
        self.assertEqual(pairing.result, Result.DOUBLE_FORFEIT)
        self.assertEqual(board.result, Result.DOUBLE_FORFEIT)
        self.assertEqual(board.result_str, str(Result.DOUBLE_FORFEIT))
        team_board = board.team_board
        assert team_board is not None
        self.assertEqual(sum(team_board.game_points), 0)

    def test_the_forfeit_win_can_be_restored(self) -> None:
        tournament = self._load()
        board = self._hole_board(tournament)
        tournament.add_result(board, self._white_result(board, Result.DOUBLE_FORFEIT))
        tournament = self._load()
        board = self._hole_board(tournament)
        tournament.add_result(board, self._white_result(board, Result.FORFEIT_WIN))
        pairing = self._hole_board(self._load()).team_forfeit_hole_pairing
        assert pairing is not None
        self.assertEqual(pairing.result, Result.FORFEIT_WIN)

    def test_no_other_result_can_be_recorded(self) -> None:
        tournament = self._load()
        board = self._hole_board(tournament)
        for player_result in (Result.WIN, Result.DRAW, Result.FORFEIT_LOSS):
            with self.assertRaises(ValueError):
                tournament.add_result(board, self._white_result(board, player_result))
