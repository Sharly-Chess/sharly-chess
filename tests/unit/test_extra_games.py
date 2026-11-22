"""The games a rule set has a team match count beyond its boards: their
score, their place in the board scores, and the end of the round."""

import contextlib
from typing import Any, ClassVar, override
from unittest import TestCase

import pytest

from data.loader import EventLoader
from data.rule_sets.rule_sets import RuleSet
from data.teams.extra_game import ExtraGameSeat
from data.teams.team_board import TeamBoard
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result, ScoreType

EVENT_ID = 'test-extra-games'
TOURNAMENT_NAME = 'tournament'


class _SecondGamesRuleSet(RuleSet):
    """The last boards are worth one point a game where the others are
    worth two, and play a second game with the colours reversed: against
    the same opponent with one such board, against the other one's with
    two."""

    def __init__(self, single_point_boards: tuple[int, ...]):
        super().__init__()
        self.single_point_boards = single_point_boards

    @staticmethod
    @override
    def static_id() -> str:
        return 'test-second-games'

    @staticmethod
    @override
    def static_name() -> str:
        return 'Second games'

    @property
    @override
    def event_type(self) -> EventType:
        return EventType.TEAM

    @override
    def board_game_points(
        self,
        board_index: int,
        board_count: int,
        team_game_points: dict[Result, float],
    ) -> dict[Result, float]:
        if board_index not in self.single_point_boards:
            return team_game_points
        return {**team_game_points, Result.WIN: 1.0}

    @override
    def extra_game_seats(self, team_board: TeamBoard) -> list[ExtraGameSeat]:
        boards = {board.index: board for board in team_board.boards}
        indexes = self.single_point_boards
        opposite = dict(zip(indexes, reversed(indexes), strict=True))
        seats = []
        for index in indexes:
            first_white_board = boards[index]
            first_black_board = boards[opposite[index]]
            seats.append(
                ExtraGameSeat(
                    key=f'{index}x{opposite[index]}',
                    label=f'{index + 1}b',
                    description=f'Board {index + 1}, second game',
                    white_board_index=opposite[index],
                    black_board_index=index,
                    white_player_id=first_black_board.black_player_id,
                    black_player_id=first_white_board.white_player_id,
                )
            )
        return seats


class ExtraGamesHarness(TestCase):
    """A round between two teams, team A with white on the first board and
    on the single-point ones."""

    rule_set: RuleSet | None = None
    rule_set_id: str | None = None
    rule_set_config: ClassVar[dict[str, Any]] = {}
    national_source: str | None = None
    pairing = 'TEAM_ROUND_ROBIN_BERGER'
    team_count = 2
    rounds = 1
    win_points = 2.0
    # The boards (0-based) a team leaves empty in round 1, by team name.
    empty_boards: ClassVar[dict[str, tuple[int, ...]]] = {}

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _create(self, boards: int, color_pattern: str) -> Tournament:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        stored_tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': self.rounds,
                'team_player_count': boards,
                'color_pattern': color_pattern,
                'pairing': self.pairing,
                'primary_score': ScoreType.MATCH_POINTS,
                'match_points': {
                    Result.WIN.value: 3.0,
                    Result.DRAW.value: 2.0,
                    Result.LOSS.value: 1.0,
                    Result.ZERO_POINT_BYE.value: 0.0,
                },
                'game_points': {
                    Result.WIN.value: self.win_points,
                    Result.DRAW.value: 0.0,
                    Result.LOSS.value: 0.0,
                },
                'rule_set': self.rule_set_id,
                'rule_set_config': dict(self.rule_set_config),
            },
        )
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            for seed in range(1, self.team_count + 1):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team {seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                for index in range(boards):
                    player_id = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{index}',
                            team_id=team_id,
                            team_index=index,
                            check_in=True,
                            national_id=f'A{seed}{index:04d}'
                            if self.national_source
                            else None,
                            national_source=self.national_source,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_id,
                            pairing_number=index + 1,
                        )
                    )
        tournament = self._load()
        with EventDatabase(EVENT_ID, write=True) as database:
            for team in tournament.teams:
                empty_boards = self.empty_boards.get(team.name, ())
                if not empty_boards:
                    continue
                team.set_round_lineup(
                    1,
                    [
                        None if index in empty_boards or player is None else player.id
                        for index, player in enumerate(team.effective_round_slots(1))
                    ],
                    database,
                )
        tournament = self._load()
        self.assertEqual(tournament.generate_round_pairings(1), '')
        return self._load()

    def _load(self) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        tournament = self._event.tournaments_by_name[TOURNAMENT_NAME]
        if self.rule_set is not None:
            tournament.__dict__['rule_set'] = self.rule_set
        return tournament

    @staticmethod
    def _match(tournament: Tournament) -> TeamBoard:
        (team_board,) = tournament.get_round_team_boards(1)
        return team_board

    def _enter(self, tournament: Tournament, team_a_results: str) -> None:
        """Enter the boards from team A's side: ``W``, ``D`` or ``L``."""
        team_board = self._match(tournament)
        results = {'W': Result.WIN, 'D': Result.DRAW, 'L': Result.LOSS}
        for board, letter in zip(team_board.boards, team_a_results, strict=True):
            result = results[letter]
            white_team_id, _black_team_id = team_board.board_team_ids(board)
            if white_team_id != team_board.stored_team_board.team_a_id:
                result = result.opposite_result
            tournament.add_result(board, result)

    def _enter_extra(
        self, tournament: Tournament, key: str, team_a_result: Result
    ) -> None:
        extra_game = self._match(tournament).extra_game(key)
        assert extra_game is not None
        tournament.set_extra_game_result(
            extra_game,
            team_a_result
            if extra_game.team_a_is_white
            else team_a_result.opposite_result,
        )


@pytest.mark.unit
class NoExtraGameTestCase(ExtraGamesHarness):
    def test_a_tournament_without_a_rule_set_has_no_extra_game(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter(tournament, 'DWWW')
        team_board = self._match(tournament)
        self.assertEqual(team_board.extra_games, [])
        self.assertEqual(team_board.game_points, (6.0, 0.0))
        self.assertTrue(tournament.is_round_finished(1))

    def test_a_rule_set_declares_none_by_default(self) -> None:
        self.rule_set = _PlainRuleSet()
        tournament = self._create(4, 'WBWW')
        self._enter(tournament, 'DWWW')
        team_board = self._match(tournament)
        self.assertEqual(team_board.extra_games, [])
        self.assertEqual(team_board.game_points, (6.0, 0.0))
        self.assertTrue(tournament.is_round_finished(1))


class _PlainRuleSet(RuleSet):
    @staticmethod
    @override
    def static_id() -> str:
        return 'test-plain'

    @staticmethod
    @override
    def static_name() -> str:
        return 'Plain'

    @property
    @override
    def event_type(self) -> EventType:
        return EventType.TEAM


@pytest.mark.unit
class OneSecondGameTestCase(ExtraGamesHarness):
    """Four boards, the last one playing twice against the same opponent."""

    rule_set = _SecondGamesRuleSet((3,))

    def test_the_second_game_reverses_the_colours(self) -> None:
        tournament = self._create(4, 'WBWW')
        team_board = self._match(tournament)
        (extra_game,) = team_board.extra_games
        last_board = team_board.boards[3]
        self.assertEqual(extra_game.seat.white_player_id, last_board.black_player_id)
        self.assertEqual(extra_game.seat.black_player_id, last_board.white_player_id)
        self.assertFalse(extra_game.team_a_is_white)

    def test_the_match_score_counts_both_games_of_the_last_board(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter(tournament, 'DWWW')
        self._enter_extra(tournament, '3x3', Result.LOSS)
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (5.0, 1.0))
        self.assertEqual(team_board.match_points_pair(), (3.0, 1.0))
        self.assertEqual(team_board.game_score_display, '5 – 1')

    def test_the_standings_count_the_second_game(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter(tournament, 'DWWW')
        self._enter_extra(tournament, '3x3', Result.LOSS)
        tournament = self._load()
        team_board = self._match(tournament)
        records = {record.team_id: record for record in tournament.team_records()}
        team_a = records[team_board.stored_team_board.team_a_id]
        team_b_id = team_board.stored_team_board.team_b_id
        assert team_b_id is not None
        team_b = records[team_b_id]
        self.assertEqual((team_a.total_mp, team_a.total_gp), (3.0, 5.0))
        self.assertEqual((team_b.total_mp, team_b.total_gp), (1.0, 1.0))

    def test_the_board_scores_add_the_second_game_to_its_board(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter(tournament, 'DWWW')
        self._enter_extra(tournament, '3x3', Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        records = {record.team_id: record for record in tournament.team_records()}
        match = records[team_board.stored_team_board.team_a_id].match_at(1)
        assert match is not None
        self.assertEqual(match.board_scores, (0.5, 1.0, 1.0, 2.0))

    def test_the_round_waits_for_the_second_game(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter(tournament, 'DWWW')
        team_board = self._match(tournament)
        self.assertFalse(team_board.all_games_played)
        self.assertFalse(tournament.is_round_finished(1))
        self.assertEqual(len(tournament.extra_games_without_result(1)), 1)
        self._enter_extra(tournament, '3x3', Result.DRAW)
        self.assertTrue(self._match(tournament).all_games_played)
        self.assertTrue(tournament.is_round_finished(1))
        self.assertEqual(tournament.extra_games_without_result(1), [])

    def test_a_drawn_second_game_makes_a_match_level_at_nothing_drawn(self) -> None:
        tournament = self._create(4, 'WBWW')
        for board in self._match(tournament).boards:
            tournament.add_result(board, Result.PENALTY_LL)
        self._enter_extra(tournament, '3x3', Result.DOUBLE_FORFEIT)
        self.assertEqual(self._match(tournament).match_points_pair(), (1.0, 1.0))
        self._enter_extra(tournament, '3x3', Result.DRAW)
        self.assertEqual(self._match(tournament).match_points_pair(), (2.0, 2.0))

    def test_a_result_is_kept_across_a_reload(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter_extra(tournament, '3x3', Result.WIN)
        tournament = self._load()
        (extra_game,) = self._match(tournament).extra_games
        self.assertEqual(extra_game.display_result_str, str(Result.WIN))

    def test_clearing_a_result_leaves_the_game_to_play(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter_extra(tournament, '3x3', Result.WIN)
        (extra_game,) = self._match(tournament).extra_games
        tournament.set_extra_game_result(extra_game, Result.NO_RESULT)
        tournament = self._load()
        (extra_game,) = self._match(tournament).extra_games
        self.assertTrue(extra_game.pending)
        self.assertEqual(tournament.stored_tournament.stored_extra_games, [])

    def test_a_match_paired_again_starts_with_its_second_game_to_play(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter_extra(tournament, '3x3', Result.WIN)
        tournament.board_operations.unpair_team(self._match(tournament))
        self.assertEqual(tournament.stored_tournament.stored_extra_games, [])
        tournament = self._load()
        self.assertEqual(tournament.stored_tournament.stored_extra_games, [])
        self.assertEqual(tournament.generate_round_pairings(1), '')
        tournament = self._load()
        (extra_game,) = self._match(tournament).extra_games
        self.assertTrue(extra_game.pending)

    def test_a_result_no_extra_game_takes_is_refused(self) -> None:
        tournament = self._create(4, 'WBWW')
        (extra_game,) = self._match(tournament).extra_games
        with self.assertRaises(ValueError):
            tournament.set_extra_game_result(extra_game, Result.ADJOURNED)

    def test_a_result_follows_its_players(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter_extra(tournament, '3x3', Result.WIN)
        team_board = self._match(tournament)
        (extra_game,) = team_board.extra_games
        other_player_id = team_board.boards[0].white_player_id
        self.rule_set = _FixedSeatRuleSet(
            ExtraGameSeat(
                key='3x3',
                label='4b',
                description='Board 4, second game',
                white_board_index=3,
                black_board_index=3,
                white_player_id=extra_game.seat.white_player_id,
                black_player_id=other_player_id,
            )
        )
        tournament = self._load()
        (changed,) = self._match(tournament).extra_games
        self.assertTrue(changed.pending)
        self.rule_set = _SecondGamesRuleSet((3,))
        tournament = self._load()
        (restored,) = self._match(tournament).extra_games
        self.assertFalse(restored.pending)

    def test_a_side_that_fields_nobody_forfeits(self) -> None:
        tournament = self._create(4, 'WBWW')
        (extra_game,) = self._match(tournament).extra_games
        self.rule_set = _FixedSeatRuleSet(
            ExtraGameSeat(
                key='3x3',
                label='4b',
                description='Board 4, second game',
                white_board_index=3,
                black_board_index=3,
                white_player_id=None,
                black_player_id=extra_game.seat.black_player_id,
            )
        )
        tournament = self._load()
        team_board = self._match(tournament)
        (forfeited,) = team_board.extra_games
        self.assertEqual(forfeited.result, Result.FORFEIT_LOSS)
        self.assertFalse(forfeited.pending)
        self.assertFalse(forfeited.team_a_is_white)
        self.assertEqual(team_board.game_points, (1.0, 0.0))
        with self.assertRaises(ValueError):
            tournament.set_extra_game_result(forfeited, Result.WIN)

    def test_an_unpublished_round_hides_the_second_game(self) -> None:
        tournament = self._create(4, 'WBWW')
        self._enter_extra(tournament, '3x3', Result.WIN)
        tournament = self._load()
        tournament.event.public_view = True
        tournament.stored_tournament.published_round = 0
        team_board = self._match(tournament)
        (extra_game,) = team_board.extra_games
        self.assertEqual(extra_game.result, Result.NO_RESULT)
        self.assertEqual(team_board.game_points, (0.0, 0.0))
        self.assertFalse(extra_game.pending)


class _FixedSeatRuleSet(_SecondGamesRuleSet):
    def __init__(self, seat: ExtraGameSeat):
        super().__init__((3,))
        self.seat = seat

    @override
    def extra_game_seats(self, team_board: TeamBoard) -> list[ExtraGameSeat]:
        return [self.seat]


@pytest.mark.unit
class CrossedSecondGamesTestCase(ExtraGamesHarness):
    """Eight boards, the last two playing a second game against each
    other's opponent."""

    rule_set = _SecondGamesRuleSet((6, 7))

    def _play(self) -> Tournament:
        tournament = self._create(8, 'WBWBWBWW')
        self._enter(tournament, 'WWLWWWLW')
        self._enter_extra(tournament, '6x7', Result.LOSS)
        self._enter_extra(tournament, '7x6', Result.LOSS)
        return tournament

    def test_each_last_board_meets_the_other_opponent(self) -> None:
        tournament = self._create(8, 'WBWBWBWW')
        team_board = self._match(tournament)
        seventh, eighth = team_board.boards[6], team_board.boards[7]
        first, second = team_board.extra_games
        self.assertEqual(
            (first.seat.white_player_id, first.seat.black_player_id),
            (eighth.black_player_id, seventh.white_player_id),
        )
        self.assertEqual(
            (second.seat.white_player_id, second.seat.black_player_id),
            (seventh.black_player_id, eighth.white_player_id),
        )

    def test_the_match_score_counts_the_four_games_of_the_last_boards(self) -> None:
        tournament = self._play()
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (11.0, 5.0))
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.point_adjustments.set_manual(
                team_board.stored_team_board.team_a_id,
                1,
                0.0,
                -2.0,
                'Two administrative forfeits',
                database,
            )
        self.assertEqual(team_board.effective_game_points, (9.0, 5.0))
        self.assertEqual(team_board.match_points_pair(), (3.0, 1.0))

    def test_each_player_scores_for_their_own_board(self) -> None:
        tournament = self._play()
        tournament = self._load()
        team_board = self._match(tournament)
        records = {record.team_id: record for record in tournament.team_records()}
        team_a = records[team_board.stored_team_board.team_a_id].match_at(1)
        team_b_id = team_board.stored_team_board.team_b_id
        assert team_b_id is not None
        team_b = records[team_b_id].match_at(1)
        assert team_a is not None and team_b is not None
        self.assertEqual(team_a.board_scores[6:], (0.0, 1.0))
        self.assertEqual(team_b.board_scores[6:], (2.0, 1.0))
