"""The rule sets of the FFE Interclubs Jeunes (J02): the score of a match
whose last boards play two games worth one point each, the forfeit
penalty, and the checks of a line-up."""

from datetime import date
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest import TestCase

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser

from common.exception import SharlyChessException
from data.player_categories import JuniorCategory, PlayerCategory
from data.teams.team_board import TeamBoard
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTieBreak, StoredTournament
from plugins.ffe import NATIONAL_SOURCE_ID
from plugins.ffe.ffe_entity import FfeLicenceTournamentCriterion
from plugins.ffe.ffe_interclubs_jeunes_rule_sets import (
    InterclubsJeunesNationale3RuleSet,
    InterclubsJeunesRuleSet,
)
from plugins.ffe.ffe_team_session import FFETeamSession, MatchReportData
from tests.unit.test_extra_games import EVENT_ID, ExtraGamesHarness
from utils.enum import Result, ScoreType


def _player(
    name: str,
    category: PlayerCategory,
    born: date,
    rating: int | None = None,
) -> Any:
    return SimpleNamespace(
        full_name=name,
        category=category,
        date_of_birth=born,
        year_of_birth=born.year,
        event_default_rating=rating,
    )


@pytest.mark.unit
class Nationale3TestCase(ExtraGamesHarness):
    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()

    def test_the_last_board_plays_its_opponent_twice(self) -> None:
        tournament = self._create(4, 'WBWB')
        team_board = self._match(tournament)
        (extra_game,) = team_board.extra_games
        last_board = team_board.boards[3]
        self.assertEqual(extra_game.key, '4-4')
        self.assertEqual(extra_game.seat.white_player_id, last_board.black_player_id)
        self.assertEqual(extra_game.seat.black_player_id, last_board.white_player_id)

    def test_a_match_counts_two_points_a_board_and_one_a_game_on_the_last(
        self,
    ) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter(tournament, 'DWWW')
        self._enter_extra(tournament, '4-4', Result.LOSS)
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (5.0, 1.0))
        self.assertEqual(team_board.match_points_pair(), (3.0, 1.0))

    def test_a_forfeit_above_a_played_board_counts_minus_two(self) -> None:
        tournament = self._create(4, 'WBWB')
        team_board = self._match(tournament)
        tournament.add_result(team_board.boards[0], Result.FORFEIT_LOSS)
        tournament.add_result(team_board.boards[1], Result.DRAW)
        tournament.add_result(team_board.boards[2], Result.WIN)
        tournament.add_result(team_board.boards[3], Result.DRAW)
        tournament = self._load()
        team_board = self._match(tournament)
        team_b = team_board.team_b
        assert team_b is not None
        rule_set = tournament.rule_set
        assert rule_set is not None
        adjustment = rule_set.team_point_adjustment(team_board.team_a, 1)
        assert adjustment is not None
        self.assertEqual(adjustment.gp, -2.0)
        self.assertIsNone(rule_set.team_point_adjustment(team_b, 1))
        self.assertEqual(team_board.game_points, (2.0, 2.0))
        self.assertEqual(team_board.effective_game_points, (0.0, 2.0))

    def test_a_penalty_does_not_take_the_score_below_zero(self) -> None:
        tournament = self._create(4, 'WBWB')
        team_board = self._match(tournament)
        tournament.add_result(team_board.boards[0], Result.FORFEIT_LOSS)
        for board in team_board.boards[1:]:
            tournament.add_result(board, Result.DRAW)
        tournament = self._load()
        team_board = self._match(tournament)
        rule_set = tournament.rule_set
        assert rule_set is not None
        adjustment = rule_set.team_point_adjustment(team_board.team_a, 1)
        assert adjustment is not None
        self.assertEqual(adjustment.gp, 0.0)
        self.assertIn('below zero', adjustment.explanation)
        self.assertEqual(team_board.effective_game_points, (0.0, 2.0))

    def test_a_forfeit_on_the_last_board_is_not_penalised(self) -> None:
        tournament = self._create(4, 'WBWB')
        team_board = self._match(tournament)
        for board in team_board.boards[:3]:
            tournament.add_result(board, Result.DRAW)
        tournament.add_result(team_board.boards[3], Result.FORFEIT_LOSS)
        self._enter_extra(tournament, '4-4', Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertIsNone(
            tournament.rule_set.team_point_adjustment(team_board.team_a, 1)  # type: ignore[union-attr]
        )


_WON, _LOST = Result.WIN, Result.LOSS
_FORFEITED, _WON_BY_FORFEIT = Result.FORFEIT_LOSS, Result.FORFEIT_WIN


def _enter_for_team_a(
    tournament: Tournament, team_board: TeamBoard, team_a_results: list[Result]
) -> None:
    """Enter the boards with the results of team A, forfeits included."""
    team_a_id = team_board.stored_team_board.team_a_id
    for board, result in zip(team_board.boards, team_a_results, strict=True):
        white_team_id, _black_team_id = team_board.board_team_ids(board)
        tournament.add_result(
            board, result if white_team_id == team_a_id else result.opposite_result
        )


def _match_points_with_adjustments(team_board: TeamBoard) -> tuple[float, float]:
    """What the two teams take from the match in the standings."""
    match_points = team_board.match_points_pair()
    assert match_points is not None
    stored_team_board = team_board.stored_team_board
    assert stored_team_board.team_b_id is not None
    adjustments = team_board.tournament.point_adjustments
    return (
        match_points[0] + adjustments.effective(stored_team_board.team_a_id, 1)[0],
        match_points[1] + adjustments.effective(stored_team_board.team_b_id, 1)[0],
    )


@pytest.mark.unit
class ForfeitedMatchTestCase(ExtraGamesHarness):
    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()

    def test_a_team_with_two_players_absent_loses_the_match_five_nil(self) -> None:
        """Team B leaves its first two boards empty, wins the third and
        loses the two games of the last."""
        tournament = self._create(4, 'WBWB')
        _enter_for_team_a(
            tournament,
            self._match(tournament),
            [_WON_BY_FORFEIT, _WON_BY_FORFEIT, _LOST, _WON],
        )
        self._enter_extra(tournament, '4-4', Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (6.0, 2.0))
        self.assertEqual(team_board.effective_game_points, (5.0, 0.0))
        self.assertEqual(_match_points_with_adjustments(team_board), (3.0, 0.0))
        team_b = team_board.team_b
        assert team_b is not None
        rule_set = tournament.rule_set
        assert rule_set is not None
        adjustment = rule_set.team_point_adjustment(team_b, 1)
        assert adjustment is not None
        self.assertIn('lost by forfeit', adjustment.explanation)

    def test_the_forfeiting_team_loses_a_match_it_was_winning(self) -> None:
        """Team A leaves its first two boards empty and wins every game
        played: 4-4 on the boards."""
        tournament = self._create(4, 'WBWB')
        _enter_for_team_a(
            tournament, self._match(tournament), [_FORFEITED, _FORFEITED, _WON, _WON]
        )
        self._enter_extra(tournament, '4-4', Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (4.0, 4.0))
        self.assertEqual(team_board.effective_game_points, (0.0, 5.0))
        self.assertEqual(_match_points_with_adjustments(team_board), (0.0, 3.0))

    def test_two_teams_over_the_limit_both_lose_the_match(self) -> None:
        tournament = self._create(4, 'WBWB')
        _enter_for_team_a(
            tournament,
            self._match(tournament),
            [_FORFEITED, _FORFEITED, _WON_BY_FORFEIT, _WON_BY_FORFEIT],
        )
        self._enter_extra(tournament, '4-4', Result.FORFEIT_WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.effective_game_points, (0.0, 0.0))
        self.assertEqual(_match_points_with_adjustments(team_board), (0.0, 0.0))

    def test_a_single_forfeit_leaves_the_match_to_its_boards(self) -> None:
        tournament = self._create(4, 'WBWB')
        _enter_for_team_a(
            tournament, self._match(tournament), [_WON_BY_FORFEIT, _LOST, _LOST, _WON]
        )
        self._enter_extra(tournament, '4-4', Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.effective_game_points, (4.0, 2.0))
        self.assertEqual(_match_points_with_adjustments(team_board), (3.0, 1.0))

    def _forfeit_by_team_b(self, tournament: Tournament) -> Tournament:
        team_board = self._match(tournament)
        team_a_id = team_board.stored_team_board.team_a_id
        for board in team_board.boards:
            white_team_id, _black_team_id = team_board.board_team_ids(board)
            tournament.add_result(
                board,
                Result.FORFEIT_WIN
                if white_team_id == team_a_id
                else Result.FORFEIT_LOSS,
            )
        self._enter_extra(tournament, '4-4', Result.FORFEIT_WIN)
        return self._load()

    def test_a_match_the_opponent_forfeits_is_won_five_nil(self) -> None:
        tournament = self._forfeit_by_team_b(self._create(4, 'WBWB'))
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (8.0, 0.0))
        self.assertEqual(team_board.effective_game_points, (5.0, 0.0))
        self.assertEqual(team_board.match_points_pair(), (3.0, 0.0))
        rule_set = tournament.rule_set
        assert rule_set is not None
        adjustment = rule_set.team_point_adjustment(team_board.team_a, 1)
        assert adjustment is not None
        self.assertIn('5-0', adjustment.explanation)

    def test_a_match_with_a_game_played_keeps_its_score(self) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter(tournament, 'WWWW')
        self._enter_extra(tournament, '4-4', Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.effective_game_points, (8.0, 0.0))


@pytest.mark.unit
class EmptyBoardTestCase(ExtraGamesHarness):
    """Team 2 names nobody on its third board."""

    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    empty_boards: ClassVar[dict[str, tuple[int, ...]]] = {'Team 2': (2,)}

    def _team_points(self, tournament: Tournament) -> tuple[float, float]:
        """The game points of team 1 and of team 2."""
        team_board = self._match(tournament)
        a_points, b_points = team_board.effective_game_points
        if team_board.team_a.name == 'Team 1':
            return a_points, b_points
        return b_points, a_points

    def _enter_for_team_1(self, tournament: Tournament, results: list[Result]) -> None:
        team_board = self._match(tournament)
        if team_board.team_a.name != 'Team 1':
            results = [result.opposite_result for result in results]
        _enter_for_team_a(tournament, team_board, results)

    def _enter_second_game_for_team_1(
        self, tournament: Tournament, result: Result
    ) -> None:
        if self._match(tournament).team_a.name != 'Team 1':
            result = result.opposite_result
        self._enter_extra(tournament, '4-4', result)

    def test_the_boards_after_an_empty_one_are_lost_whatever_was_played(self) -> None:
        """Team 2 wins the first two boards and both games of the last
        one, which comes after the empty board."""
        tournament = self._create(4, 'WBWB')
        self._enter_for_team_1(tournament, [_LOST, _LOST, _WON_BY_FORFEIT, _LOST])
        self._enter_second_game_for_team_1(tournament, Result.LOSS)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(sorted(team_board.game_points), [2.0, 6.0])
        self.assertEqual(self._team_points(tournament), (4.0, 4.0))
        (extra_game,) = team_board.extra_games
        self.assertTrue(extra_game.played)

    def test_a_board_lost_after_an_empty_one_changes_nothing(self) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter_for_team_1(tournament, [_LOST, _LOST, _WON_BY_FORFEIT, _WON])
        self._enter_second_game_for_team_1(tournament, Result.WIN)
        tournament = self._load()
        self.assertEqual(self._team_points(tournament), (4.0, 4.0))
        team_board = self._match(tournament)
        rule_set = tournament.rule_set
        assert rule_set is not None
        self.assertIsNone(rule_set.team_point_adjustment(team_board.team_a, 1))

    def test_an_empty_board_is_not_a_forfeit_penalised_above_a_played_board(
        self,
    ) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter_for_team_1(tournament, [_LOST, _LOST, _WON_BY_FORFEIT, _WON])
        self._enter_second_game_for_team_1(tournament, Result.WIN)
        tournament = self._load()
        team_board = self._match(tournament)
        rule_set = tournament.rule_set
        assert rule_set is not None
        team_b = team_board.team_b
        assert team_b is not None
        for team in (team_board.team_a, team_b):
            self.assertIsNone(rule_set.team_point_adjustment(team, 1))


@pytest.mark.unit
class LeagueForfeitedMatchTestCase(ExtraGamesHarness):
    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    rule_set_config: ClassVar[dict[str, Any]] = {'second_games': 'none'}

    def test_a_format_of_a_league_has_no_score_for_a_forfeited_match(self) -> None:
        tournament = self._create(4, 'WBWB')
        team_board = self._match(tournament)
        team_a_id = team_board.stored_team_board.team_a_id
        for board in team_board.boards:
            white_team_id, _black_team_id = team_board.board_team_ids(board)
            tournament.add_result(
                board,
                Result.FORFEIT_WIN
                if white_team_id == team_a_id
                else Result.FORFEIT_LOSS,
            )
        tournament = self._load()
        self.assertEqual(self._match(tournament).effective_game_points, (8.0, 0.0))


@pytest.mark.unit
class RankingTestCase(ExtraGamesHarness):
    """Three teams level on match points, each having beaten one of the
    others."""

    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    team_count = 3
    rounds = 3

    @staticmethod
    def _round_match(tournament: Tournament, round_: int) -> TeamBoard:
        (team_board,) = (
            team_board
            for team_board in tournament.get_round_team_boards(round_)
            if team_board.team_b is not None
        )
        return team_board

    def test_the_results_between_the_tied_teams_rank_them(self) -> None:
        """The first beats the second 7-0, which beats the third 2-0, which
        beats the first 2-0: level on match points, they are ranked on
        their differentials, +5, 0 and -5."""
        tournament = self._create(4, 'WBWB')
        rule_set = tournament.rule_set
        assert rule_set is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_all_tournament_stored_tie_breaks(tournament.id)
            for index, (type_, options) in enumerate(
                rule_set.tie_breaks_for_pairing('TEAM_ROUND_ROBIN')
            ):
                database.add_stored_tie_break(
                    StoredTieBreak(
                        id=None,
                        tournament_id=tournament.id,
                        type=type_,
                        options=dict(options),
                        index=index,
                    )
                )
        tournament = self._load()
        opening = self._round_match(tournament, 1).stored_team_board
        first, second = opening.team_a_id, opening.team_b_id
        (third,) = {team.id for team in tournament.teams} - {first, second}
        beats = {first: second, second: third, third: first}
        for round_ in (1, 2, 3):
            if round_ > 1:
                self.assertEqual(tournament.generate_round_pairings(round_), '')
                tournament = self._load()
            team_board = self._round_match(tournament, round_)
            stored = team_board.stored_team_board
            winner = (
                stored.team_a_id
                if beats[stored.team_a_id] == stored.team_b_id
                else stored.team_b_id
            )
            for index, board in enumerate(team_board.boards):
                white_team_id, _black_team_id = team_board.board_team_ids(board)
                if index == 0 or winner == first:
                    result = Result.WIN if white_team_id == winner else Result.LOSS
                else:
                    result = Result.DRAW
                tournament.add_result(board, result)
            (extra_game,) = team_board.extra_games
            tournament.set_extra_game_result(extra_game, Result.DRAW)
            tournament = self._load()
        tournament = self._load()
        standings = tournament.team_standings()
        self.assertEqual([standing.mp for standing in standings], [4.0, 4.0, 4.0])
        self.assertEqual(
            [standing.team.id for standing in standings], [first, third, second]
        )


@pytest.mark.unit
class NationalDivisionsTestCase(ExtraGamesHarness):
    rule_set_id = InterclubsJeunesRuleSet.static_id()

    def test_the_last_two_boards_meet_each_other_s_opponent(self) -> None:
        tournament = self._create(8, 'WBWBWBWW')
        team_board = self._match(tournament)
        seventh, eighth = team_board.boards[6], team_board.boards[7]
        first, second = team_board.extra_games
        self.assertEqual((first.key, second.key), ('7-8', '8-7'))
        self.assertEqual(
            (first.seat.white_player_id, first.seat.black_player_id),
            (eighth.black_player_id, seventh.white_player_id),
        )
        self.assertEqual(
            (second.seat.white_player_id, second.seat.black_player_id),
            (seventh.black_player_id, eighth.white_player_id),
        )

    def test_a_match_counts_the_four_games_of_the_last_boards(self) -> None:
        tournament = self._create(8, 'WBWBWBWW')
        self._enter(tournament, 'WWLWWWLW')
        self._enter_extra(tournament, '7-8', Result.LOSS)
        self._enter_extra(tournament, '8-7', Result.LOSS)
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

    def test_three_players_absent_leave_the_match_to_its_boards(self) -> None:
        tournament = self._create(8, 'WBWBWBWW')
        _enter_for_team_a(
            tournament,
            self._match(tournament),
            [_WON_BY_FORFEIT] * 3 + [_LOST] * 5,
        )
        self._enter_extra(tournament, '7-8', Result.LOSS)
        self._enter_extra(tournament, '8-7', Result.LOSS)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.effective_game_points, (6.0, 4.0))
        self.assertEqual(_match_points_with_adjustments(team_board), (3.0, 1.0))

    def test_four_players_absent_lose_the_match_ten_nil(self) -> None:
        tournament = self._create(8, 'WBWBWBWW')
        _enter_for_team_a(
            tournament,
            self._match(tournament),
            [_WON_BY_FORFEIT] * 4 + [_LOST] * 4,
        )
        self._enter_extra(tournament, '7-8', Result.LOSS)
        self._enter_extra(tournament, '8-7', Result.LOSS)
        tournament = self._load()
        team_board = self._match(tournament)
        self.assertEqual(team_board.game_points, (8.0, 8.0))
        self.assertEqual(team_board.effective_game_points, (10.0, 0.0))
        self.assertEqual(_match_points_with_adjustments(team_board), (3.0, 0.0))


@pytest.mark.unit
class LeagueFormatTestCase(ExtraGamesHarness):
    """A Nationale 3 whose league set its own format."""

    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    rule_set_config: ClassVar[dict[str, Any]] = {'second_games': 'last-two-boards'}
    win_points = 4.0

    def test_the_last_two_of_six_boards_meet_each_other_s_opponent(self) -> None:
        tournament = self._create(6, 'WBWBWB')
        team_board = self._match(tournament)
        fifth, sixth = team_board.boards[4], team_board.boards[5]
        first, second = team_board.extra_games
        self.assertEqual((first.key, second.key), ('5-6', '6-5'))
        self.assertEqual(
            (first.seat.white_player_id, first.seat.black_player_id),
            (sixth.white_player_id, fifth.white_player_id),
        )

    def test_a_game_of_a_board_that_plays_twice_is_worth_half(self) -> None:
        tournament = self._create(6, 'WBWBWB')
        self._enter(tournament, 'WDDDWL')
        self._enter_extra(tournament, '5-6', Result.WIN)
        self._enter_extra(tournament, '6-5', Result.LOSS)
        self.assertEqual(self._match(tournament).game_points, (8.0, 4.0))


@pytest.mark.unit
class SwissLeagueTestCase(ExtraGamesHarness):
    """A Nationale 3 of a league with more teams than rounds, paired as a
    Swiss."""

    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    pairing = 'TEAM_SWISS_STANDARD'
    team_count = 4

    def test_every_match_of_a_swiss_round_has_its_second_game(self) -> None:
        tournament = self._create(4, 'WBWB')
        team_boards = tournament.get_round_team_boards(1)
        self.assertEqual(len(team_boards), 2)
        for team_board in team_boards:
            (extra_game,) = team_board.extra_games
            self.assertEqual(extra_game.key, '4-4')
            for board in team_board.boards:
                tournament.add_result(board, Result.DRAW)
        self.assertFalse(tournament.is_round_finished(1))
        for team_board in team_boards:
            (extra_game,) = team_board.extra_games
            tournament.set_extra_game_result(extra_game, Result.WIN)
            self.assertEqual(sorted(team_board.game_points), [0.0, 1.0])
        self.assertTrue(tournament.is_round_finished(1))


@pytest.mark.unit
class NoSecondGameTestCase(ExtraGamesHarness):
    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    rule_set_config: ClassVar[dict[str, Any]] = {'second_games': 'none'}

    def test_every_board_plays_one_game_worth_the_same(self) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter(tournament, 'DDDW')
        team_board = self._match(tournament)
        self.assertEqual(team_board.extra_games, [])
        self.assertEqual(team_board.game_points, (2.0, 0.0))
        self.assertTrue(tournament.is_round_finished(1))


class _UploadHarness(ExtraGamesHarness):
    national_source = NATIONAL_SOURCE_ID

    def _report(self, tournament: Tournament) -> MatchReportData:
        tournament = self._load()
        (match,) = FFETeamSession.round_matches(tournament, 1)
        team_board = self._match(tournament)
        team_b_id = team_board.stored_team_board.team_b_id
        assert team_b_id is not None
        return FFETeamSession.match_report_data(
            match, 1, {team_board.stored_team_board.team_a_id: 11, team_b_id: 12}
        )


@pytest.mark.unit
class Nationale3UploadTestCase(_UploadHarness):
    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()

    def test_the_report_lists_the_last_board_twice(self) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter(tournament, 'DWWW')
        self._enter_extra(tournament, '4-4', Result.LOSS)
        report = self._report(tournament)
        self.assertEqual(report.left_team_id, 11)
        self.assertEqual(
            report.boards,
            [
                ('A10000', 'A20000', 'Nulle'),
                ('A10001', 'A20001', 'GainBlanc'),
                ('A10002', 'A20002', 'GainBlanc'),
                ('A10003', 'A20003', 'GainBlanc'),
                ('A10003', 'A20003', 'GainNoir'),
            ],
        )
        self.assertEqual(report.extra_game_count, 1)
        self.assertEqual(
            (report.left_game_points, report.right_game_points), ('5.0', '1.0')
        )
        self.assertEqual(
            (report.left_match_points, report.right_match_points), ('3', '1')
        )

    def test_a_second_game_still_to_play_is_sent_without_a_result(self) -> None:
        tournament = self._create(4, 'WBWB')
        self._enter(tournament, 'DWWW')
        report = self._report(tournament)
        self.assertEqual(report.boards[4], ('A10003', 'A20003', 'None'))

    def test_a_report_with_too_few_lines_is_refused(self) -> None:
        tournament = self._create(4, 'WBWB')
        report = self._report(tournament)
        session = FFETeamSession(tournament=None)
        session._get = lambda url: AdvancedHTMLParser()  # type: ignore[method-assign]
        session.parse_board_count = lambda parser: 4  # type: ignore[method-assign]
        with self.assertRaises(SharlyChessException):
            session.save_report(4310, report)


@pytest.mark.unit
class EmptyBoardUploadTestCase(_UploadHarness):
    """Team 2 names nobody on its third board, and wins both games of its
    fourth."""

    rule_set_id = InterclubsJeunesNationale3RuleSet.static_id()
    empty_boards: ClassVar[dict[str, tuple[int, ...]]] = {'Team 2': (2,)}

    def test_the_games_after_an_empty_board_keep_their_result_beside_the_forfeit(
        self,
    ) -> None:
        tournament = self._create(4, 'WBWB')
        team_board = self._match(tournament)
        team_1_is_a = team_board.team_a.name == 'Team 1'
        results = [_WON, _WON, _WON_BY_FORFEIT, _LOST]
        if not team_1_is_a:
            results = [result.opposite_result for result in results]
        _enter_for_team_a(tournament, team_board, results)
        self._enter_extra(tournament, '4-4', Result.LOSS if team_1_is_a else Result.WIN)
        report = self._report(tournament)
        team_1_is_left = report.boards[0][0].startswith('A1')
        won, forfeit, kept = (
            ('GainBlanc', 'GainBlancForfait', 'AdminNoirGainNoir')
            if team_1_is_left
            else ('GainNoir', 'GainNoirForfait', 'AdminBlancGainBlanc')
        )
        self.assertEqual(
            [line[2] for line in report.boards], [won, won, forfeit, kept, kept]
        )
        team_1_points, team_2_points = (
            (report.left_game_points, report.right_game_points)
            if team_1_is_left
            else (report.right_game_points, report.left_game_points)
        )
        self.assertEqual((team_1_points, team_2_points), ('8.0', '0.0'))


@pytest.mark.unit
class AdministrativeResultTestCase(TestCase):
    def test_a_game_keeps_its_result_beside_the_forfeit_of_either_team(self) -> None:
        convert = FFETeamSession._administrative_site_result
        self.assertEqual(convert('Nulle', False, False), 'Nulle')
        self.assertEqual(convert('Nulle', True, False), 'AdminBlancNulle')
        self.assertEqual(convert('GainBlanc', False, True), 'AdminNoirGainBlanc')
        self.assertEqual(convert('GainNoir', True, True), 'AdminDoubleGainNoir')

    def test_a_board_won_by_forfeit_is_lost_by_a_team_that_forfeits_it_too(
        self,
    ) -> None:
        convert = FFETeamSession._administrative_site_result
        self.assertEqual(
            convert('GainBlancForfait', True, False), 'AdminBlancForfaitNoir'
        )
        self.assertEqual(
            convert('GainNoirForfait', False, True), 'AdminNoirForfaitBlanc'
        )
        self.assertEqual(convert('GainBlancForfait', False, True), 'GainBlancForfait')
        self.assertEqual(convert('None', True, True), 'None')


@pytest.mark.unit
class NationalDivisionsUploadTestCase(_UploadHarness):
    rule_set_id = InterclubsJeunesRuleSet.static_id()

    def test_the_report_lists_the_crossed_games_after_the_boards(self) -> None:
        tournament = self._create(8, 'WBWBWBWW')
        self._enter(tournament, 'WWLWWWLW')
        self._enter_extra(tournament, '7-8', Result.LOSS)
        self._enter_extra(tournament, '8-7', Result.WIN)
        report = self._report(tournament)
        self.assertEqual(len(report.boards), 10)
        self.assertEqual(
            report.boards[6:],
            [
                ('A10006', 'A20006', 'GainNoir'),
                ('A10007', 'A20007', 'GainBlanc'),
                ('A10006', 'A20007', 'GainNoir'),
                ('A10007', 'A20006', 'GainBlanc'),
            ],
        )
        self.assertEqual(report.extra_game_count, 2)


@pytest.mark.unit
class DefaultsTestCase(TestCase):
    def test_the_division_names_the_one_of_the_federation_site(self) -> None:
        self.assertEqual(InterclubsJeunesRuleSet.ffe_competition_id(), 3)
        self.assertEqual(
            InterclubsJeunesRuleSet({'division': 'top-jeunes'}).ffe_division_name,
            'Top Jeunes',
        )
        self.assertIsNone(InterclubsJeunesNationale3RuleSet.ffe_competition_id())

    @staticmethod
    def _stored() -> StoredTournament:
        return cast(
            StoredTournament,
            SimpleNamespace(
                criteria={},
                game_points=None,
                match_points=None,
                pairing='',
                rounds=5,
                team_player_count=6,
                color_pattern='WBWBWW',
                cadence=None,
                primary_score=None,
            ),
        )

    def test_the_national_divisions_impose_the_format_and_the_scoring(self) -> None:
        rule_set = InterclubsJeunesRuleSet()
        stored = self._stored()
        rule_set.apply_defaults(stored, 'TEAM_ROUND_ROBIN')
        self.assertEqual(stored.team_player_count, 8)
        self.assertEqual(stored.color_pattern, 'WBWBWBWW')
        self.assertEqual(stored.primary_score, ScoreType.MATCH_POINTS.value)
        self.assertEqual(stored.rounds, 0)
        assert stored.game_points is not None
        assert stored.match_points is not None
        self.assertEqual(stored.game_points[Result.WIN.value], 2.0)
        self.assertEqual(stored.match_points[Result.LOSS.value], 1.0)
        self.assertIn('team_player_count', rule_set.managed_fields)
        self.assertIn('cadence', rule_set.managed_fields)
        self.assertEqual(
            rule_set.form_defaults('TEAM_ROUND_ROBIN')['color_pattern'], 'WBWBWBWW'
        )

    def test_the_nationale_3_suggests_everything_and_imposes_nothing(self) -> None:
        rule_set = InterclubsJeunesNationale3RuleSet()
        stored = self._stored()
        rule_set.apply_defaults(stored, 'TEAM_ROUND_ROBIN')
        self.assertEqual(stored.team_player_count, 6)
        self.assertEqual(stored.color_pattern, 'WBWBWW')
        self.assertIsNone(stored.game_points)
        self.assertIsNone(stored.cadence)
        self.assertEqual(stored.rounds, 5)
        self.assertEqual(stored.criteria, {})
        self.assertEqual(rule_set.managed_fields, set())
        self.assertEqual(rule_set.form_defaults('TEAM_ROUND_ROBIN'), {})
        self.assertIsNone(rule_set.rounds_for_pairing('TEAM_ROUND_ROBIN'))
        prefills = rule_set.form_prefills()
        self.assertEqual(prefills['team_player_count'], '4')
        self.assertEqual(prefills['color_pattern'], 'WBWB')
        self.assertEqual(prefills['gp_win'], '2')
        self.assertEqual(prefills['mp_zpb'], '0')
        self.assertEqual(prefills['secondary_score_for_colours'], 'on')
        self.assertIn(FfeLicenceTournamentCriterion().form_key, prefills)

    def test_the_nationale_3_starts_with_its_criteria_and_leaves_them_open(
        self,
    ) -> None:
        self.assertTrue(InterclubsJeunesRuleSet().imposes_tie_breaks)
        nationale_3 = InterclubsJeunesNationale3RuleSet()
        self.assertFalse(nationale_3.imposes_tie_breaks)
        self.assertTrue(nationale_3.tie_breaks_for_pairing('TEAM_ROUND_ROBIN'))

    def test_only_the_national_divisions_require_the_round_robin(self) -> None:
        self.assertEqual(
            InterclubsJeunesRuleSet().required_pairing_system_id, 'TEAM_ROUND_ROBIN'
        )
        nationale_3 = InterclubsJeunesNationale3RuleSet()
        self.assertIsNone(nationale_3.required_pairing_system_id)
        self.assertEqual(
            nationale_3.form_prefills()['pairing_system'], 'TEAM_ROUND_ROBIN'
        )
        self.assertEqual(next(iter(nationale_3.form_prefills())), 'pairing_system')
        self.assertTrue(nationale_3.tie_breaks_for_pairing('TEAM_SWISS'))

    def test_the_rule_sets_are_kept_and_not_exported(self) -> None:
        for rule_set in (
            InterclubsJeunesRuleSet(),
            InterclubsJeunesNationale3RuleSet(),
        ):
            self.assertTrue(rule_set.forbids_exports)
            self.assertTrue(rule_set.locked_once_paired)


@pytest.mark.unit
class LineupWarningsTestCase(TestCase):
    def test_a_board_takes_a_player_of_its_category_or_younger(self) -> None:
        rule_set = InterclubsJeunesNationale3RuleSet()
        lineup = [
            _player('Sixteen', JuniorCategory(16), date(2011, 1, 1)),
            _player('Sixteen too', JuniorCategory(16), date(2011, 6, 1)),
            _player('Ten', JuniorCategory(10), date(2017, 1, 1)),
            None,
        ]
        (warning,) = rule_set._age_category_warnings(
            lineup, rule_set.board_age_limits(4)
        )
        self.assertIn('Sixteen too', warning)
        self.assertIn('Board 2', warning)

    def test_a_format_of_a_league_has_no_age_category_to_check(self) -> None:
        self.assertIsNone(InterclubsJeunesNationale3RuleSet().board_age_limits(6))
        self.assertIsNone(
            InterclubsJeunesNationale3RuleSet(
                {'second_games': 'none'}
            ).board_age_limits(4)
        )
        self.assertEqual(
            InterclubsJeunesNationale3RuleSet()._age_category_warnings(
                [_player('Adult', JuniorCategory(20), date(2006, 1, 1))], None
            ),
            [],
        )

    def test_a_younger_player_sits_above_an_older_one_with_a_rating_as_high(
        self,
    ) -> None:
        rule_set = InterclubsJeunesNationale3RuleSet()
        older = _player('Older', JuniorCategory(14), date(2013, 1, 1), 1500)
        self.assertEqual(
            rule_set._board_order_warnings(
                [_player('Younger', JuniorCategory(14), date(2014, 1, 1), 1500), older],
                (),
            ),
            [],
        )
        (warning,) = rule_set._board_order_warnings(
            [_player('Younger', JuniorCategory(14), date(2014, 1, 1), 1400), older], ()
        )
        self.assertIn('Younger', warning)
        self.assertIn('Older', warning)

    def test_the_boards_that_play_twice_sit_either_way_round(self) -> None:
        rule_set = InterclubsJeunesRuleSet()
        lineup: list[Any] = [None] * 6 + [
            _player('Younger', JuniorCategory(10), date(2018, 1, 1), 1000),
            _player('Older', JuniorCategory(10), date(2017, 1, 1), 1200),
        ]
        self.assertEqual(
            rule_set._board_order_warnings(lineup, rule_set.second_game_boards(8)), []
        )
