"""The points a tournament awards: the FIDE defaults, and what an
arbiter's overrides change."""

import pytest

from data.point_system import PointSystem
from utils.enum import Result, ScoreType


def _individual(**overrides: float) -> PointSystem:
    return PointSystem(
        game_point_overrides={Result[k].value: v for k, v in overrides.items()},
        match_point_overrides={},
        is_team=False,
        boards=0,
        pab_is_draw=False,
        bye_is_rest=False,
        primary_score=ScoreType.MATCH_POINTS,
    )


def _team(
    *,
    boards: int = 4,
    pab_is_draw: bool = True,
    bye_is_rest: bool = False,
    game: dict[str, float] | None = None,
    match: dict[str, float] | None = None,
) -> PointSystem:
    return PointSystem(
        game_point_overrides={Result[k].value: v for k, v in (game or {}).items()},
        match_point_overrides={Result[k].value: v for k, v in (match or {}).items()},
        is_team=True,
        boards=boards,
        pab_is_draw=pab_is_draw,
        bye_is_rest=bye_is_rest,
        primary_score=ScoreType.MATCH_POINTS,
    )


@pytest.mark.unit
class TestIndividualGamePoints:
    def test_the_defaults_are_fide_s(self):
        system = _individual()
        assert (system.win, system.draw, system.loss) == (1.0, 0.5, 0.0)
        assert system.pab == 1.0
        assert system.zpb == 0.0
        assert system.is_standard

    def test_a_bye_follows_the_result_it_stands_for_unless_set(self):
        system = _individual(WIN=3, DRAW=1, LOSS=-1)
        assert system.pab == 3.0
        assert system.zpb == -1.0
        assert not system.is_standard
        assert _individual(PAIRING_ALLOCATED_BYE=0.5).pab == 0.5

    def test_the_pab_is_expressed_as_the_result_it_is_worth(self):
        assert _individual().pab_equivalent_result == Result.WIN
        assert (
            _individual(PAIRING_ALLOCATED_BYE=0.5).pab_equivalent_result == Result.DRAW
        )
        assert _individual(PAIRING_ALLOCATED_BYE=0).pab_equivalent_result == Result.LOSS
        assert (
            _individual(PAIRING_ALLOCATED_BYE=0.75).pab_equivalent_result == Result.WIN
        )

    def test_an_individual_tournament_awards_no_match_points(self):
        assert _individual().match_points == {}


@pytest.mark.unit
class TestTeamPoints:
    def test_board_games_keep_the_fide_defaults_whatever_the_override(self):
        system = _team(game={'WIN': 3, 'DRAW': 2, 'LOSS': 1})
        assert system.game_points[Result.WIN] == 1.0
        assert system.team_game_points[Result.WIN] == 3.0

    def test_a_forfeit_is_worth_the_absent_override(self):
        system = _team(game={'ZERO_POINT_BYE': -1})
        assert system.team_game_points[Result.FORFEIT_LOSS] == -1.0
        assert system.team_game_points[Result.DOUBLE_FORFEIT] == -1.0
        assert _team().team_game_points[Result.FORFEIT_LOSS] == 0.0

    def test_match_points_default_to_the_olympiad_values(self):
        assert _team().match_points == {
            Result.WIN: 2.0,
            Result.DRAW: 1.0,
            Result.LOSS: 0.0,
            Result.ZERO_POINT_BYE: 0.0,
            Result.PAIRING_ALLOCATED_BYE: 1.0,
        }

    def test_a_team_pab_is_a_draw_under_swiss_and_a_win_elsewhere(self):
        assert _team(pab_is_draw=True).match_points[Result.PAIRING_ALLOCATED_BYE] == 1.0
        assert (
            _team(pab_is_draw=False).match_points[Result.PAIRING_ALLOCATED_BYE] == 2.0
        )
        assert _team(boards=4, pab_is_draw=True).team_pab_game_points == 2.0
        assert _team(boards=4, pab_is_draw=False).team_pab_game_points == 4.0

    def test_a_team_pab_scales_with_the_board_values(self):
        assert (
            _team(boards=4, pab_is_draw=False, game={'WIN': 3}).team_pab_game_points
            == 12.0
        )
        assert (
            _team(boards=4, game={'PAIRING_ALLOCATED_BYE': 1.5}).team_pab_game_points
            == 1.5
        )

    def test_the_secondary_score_is_whichever_is_not_primary(self):
        assert _team().secondary_score == ScoreType.GAME_POINTS
        system = PointSystem(
            game_point_overrides={},
            match_point_overrides={},
            is_team=True,
            boards=4,
            pab_is_draw=True,
            bye_is_rest=False,
            primary_score=ScoreType.GAME_POINTS,
        )
        assert system.secondary_score == ScoreType.MATCH_POINTS
