from abc import ABC
from functools import cache

from common.i18n import _
from data.pairings.settings import PairingSetting
from data.pairings.variations import SwissVariation
from data.player import Player
from data.tournament import Tournament
from plugins.pairing_acceleration import PLUGIN_NAME
from plugins.pairing_acceleration.pairing_settings import (
    RatingLimitSetting,
    DualRatingLimitsSetting,
    RatingGroup,
)
from utils.enum import Result


class AccelerationSwissVariation(SwissVariation, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-{super().static_id()}'


class HaleySwissVariation(AccelerationSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY'

    @staticmethod
    def static_name() -> str:
        return _('Haley system')

    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [RatingLimitSetting()]

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        if at_round <= 2:
            rating_group = RatingLimitSetting.get_player_rating_group(
                tournament, player
            )
            if rating_group == RatingGroup.A:
                return Result.GAIN.points(tournament.point_values)
        return 0.0

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= 2


class HaleySoftSwissVariation(AccelerationSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY_SOFT'

    @staticmethod
    def static_name() -> str:
        return _('Soft Haley system')

    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [RatingLimitSetting()]

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        # Round 1: Group A gets 1 vpoint
        # Round 2: Group A gets 1 vpoint, Group B gets .5 vpoints
        # Round 2: All other players get .5 vpoints
        if at_round <= 2:
            rating_group = RatingLimitSetting.get_player_rating_group(
                tournament, player
            )
            if rating_group == RatingGroup.A:
                return Result.GAIN.points(tournament.point_values)
            elif at_round == 2:
                return Result.DRAW.points(tournament.point_values)
        return 0.0

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= 2


class ProgressiveSwissVariation(AccelerationSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'PROGRESSIVE'

    @staticmethod
    def static_name() -> str:
        return _('Progressive accelerated system')

    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [DualRatingLimitsSetting()]

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return 0.0
        return cls._compute_virtual_points(
            rating_group=DualRatingLimitsSetting.get_player_rating_group(
                tournament, player
            ),
            tournament_rounds=tournament.rounds,
            points=player.points_before(at_round),
            draw_points=Result.DRAW.points(tournament.point_values),
            gain_points=Result.GAIN.points(tournament.point_values),
        )

    @staticmethod
    @cache
    def _compute_virtual_points(
        rating_group: RatingGroup,
        tournament_rounds: int,
        points: float,
        draw_points: float,
        gain_points: float,
    ) -> float:
        if 2 * points >= tournament_rounds * gain_points:
            # If a player gets at least half the possible score,
            # their capital is set at 2 points.
            return 2 * gain_points

        # Players get a virtual draw points for real draw points
        vpoints = draw_points * (points // (3 * draw_points))

        # Starting points: Group A - 2, Group B - 1, Group C - 0
        match rating_group:
            case RatingGroup.A:
                vpoints += 2 * gain_points
            case RatingGroup.B:
                vpoints += gain_points

        # Players cannot have more than 2 virtual points
        return min(2 * gain_points, vpoints)

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= rounds - 2
