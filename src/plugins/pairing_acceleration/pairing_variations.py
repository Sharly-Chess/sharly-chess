from abc import ABC, abstractmethod
from functools import cache, partial
from typing import Callable

from common.i18n import _
from data.pairings.settings import PairingSetting
from data.pairings.variations import SwissVariation
from data.player import Player
from data.tournament import Tournament
from plugins.pairing_acceleration import PLUGIN_NAME
from plugins.pairing_acceleration.pairing_settings import (
    AccelerationGroup,
    GroupA2GroupsSetting,
    GroupB2GroupsSetting,
    GroupA3GroupsSetting,
    GroupB3GroupsSetting,
    GroupC3GroupsSetting,
)
from utils import StaticUtils
from utils.enum import Result


class AccelerationSwissVariation(SwissVariation, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-{super().static_id()}'

    @classmethod
    @abstractmethod
    def _get_group_a_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        """Tooltip representing the group A."""

    @classmethod
    @abstractmethod
    def _get_group_b_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        """Tooltip representing the group B."""

    @classmethod
    def get_group_a_tooltip(cls, tournament: Tournament) -> str:
        return cls._build_tooltip(cls._get_group_a_tooltip_lines(tournament))

    @classmethod
    def get_group_b_tooltip(cls, tournament: Tournament) -> str:
        return cls._build_tooltip(cls._get_group_b_tooltip_lines(tournament))

    @staticmethod
    def _build_tooltip(tooltip_lines: list[str]) -> str:
        if not tooltip_lines:
            return _('No acceleration.')
        title = f'<h6>{_("Virtual points")}</h6>'
        return title + ''.join(
            f'<div class="text-start">{line}</div>' for line in tooltip_lines
        )

    @staticmethod
    def _round_range_tooltip_line(
        min_round: int,
        max_round: int | None = None,
        points: float = 0.0,
        message: str | None = None,
    ) -> str:
        if not max_round or min_round >= max_round:
            prefix = _('Round {round}').format(round=min_round)
        else:
            prefix = _('Rounds {min_round}-{max_round}').format(
                min_round=min_round, max_round=max_round
            )
        if not message:
            message = StaticUtils.points_str(points)
        return _('{string}: {value}').format(string=prefix, value=message)

    @classmethod
    @abstractmethod
    def get_player_group(
        cls, tournament: Tournament, player: Player
    ) -> AccelerationGroup:
        """Get the acceleration group of a player in a tournament."""


class Acceleration2GroupsSwissVariation(AccelerationSwissVariation, ABC):
    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [
            GroupA2GroupsSetting(),
            GroupB2GroupsSetting(),
        ]

    @classmethod
    def get_player_group(
        cls, tournament: Tournament, player: Player
    ) -> AccelerationGroup:
        _, group_a_max = tournament.pairing_settings[GroupA2GroupsSetting.static_id()]
        if player.pairing_number <= group_a_max:
            return AccelerationGroup.A
        return AccelerationGroup.B


class Acceleration3GroupsSwissVariation(AccelerationSwissVariation, ABC):
    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [
            GroupA3GroupsSetting(),
            GroupB3GroupsSetting(),
            GroupC3GroupsSetting(),
        ]

    @classmethod
    @abstractmethod
    def _get_group_c_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        """Tooltip representing the group C."""

    @classmethod
    def get_group_c_tooltip(cls, tournament: Tournament) -> str:
        return cls._build_tooltip(cls._get_group_c_tooltip_lines(tournament))

    @classmethod
    def get_player_group(
        cls, tournament: Tournament, player: Player
    ) -> AccelerationGroup:
        _, group_a_max = tournament.pairing_settings[GroupA3GroupsSetting.static_id()]
        if player.pairing_number <= group_a_max:
            return AccelerationGroup.A
        _, group_b_max = tournament.pairing_settings[GroupB3GroupsSetting.static_id()]
        if player.pairing_number <= group_b_max:
            return AccelerationGroup.B
        return AccelerationGroup.C

    @staticmethod
    def _format_vpoints_inequality(
        vpoints: float,
        min_points: float | None = None,
        max_points: float | None = None,
    ) -> str:
        points_name = _('points')
        min_str = StaticUtils.points_str(min_points)
        max_str = StaticUtils.points_str(max_points)
        if not min_points:
            inequality = f'{points_name} < {max_str}'
        elif not max_points:
            inequality = f'{points_name} ≥ {min_str}'
        else:
            inequality = f'{min_str} ≤ {points_name} < {max_str}'
        return _('{string}: {value}').format(
            string=inequality, value=StaticUtils.points_str(vpoints)
        )

    @classmethod
    def _get_incremental_points_message(
        cls,
        get_vpoints: Callable[[float], float],
        step: float,
        max_vpoints: float,
    ) -> str:
        message_parts: list[str] = []
        points = 0.0
        previous_threshold: float | None = None
        previous_vpoints = get_vpoints(points)
        vpoints = previous_vpoints
        while vpoints < max_vpoints:
            points += step
            vpoints = get_vpoints(points)
            if previous_vpoints != vpoints:
                message_parts.append(
                    cls._format_vpoints_inequality(
                        previous_vpoints, previous_threshold, points
                    )
                )
                previous_threshold = points
                previous_vpoints = vpoints

        message_parts.append(cls._format_vpoints_inequality(vpoints, points))
        return ''.join('<br/>&nbsp;&nbsp;' + part for part in message_parts)


class HaleySwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY'

    @staticmethod
    def static_name() -> str:
        return _('Haley system')

    @classmethod
    def _get_group_a_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return [
            cls._round_range_tooltip_line(
                1, 2, Result.WIN.points(tournament.point_values)
            ),
            cls._round_range_tooltip_line(3, tournament.rounds),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return []

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        if at_round <= 2:
            group = cls.get_player_group(tournament, player)
            if group == AccelerationGroup.A:
                return Result.WIN.points(tournament.point_values)
        return 0.0

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= 2


class HaleySoftSwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY_SOFT'

    @staticmethod
    def static_name() -> str:
        return _('Soft Haley system')

    @classmethod
    def _get_group_a_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return [
            cls._round_range_tooltip_line(
                1, 2, Result.WIN.points(tournament.point_values)
            ),
            cls._round_range_tooltip_line(3, tournament.rounds),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return [
            cls._round_range_tooltip_line(1),
            cls._round_range_tooltip_line(
                2, points=Result.DRAW.points(tournament.point_values)
            ),
            cls._round_range_tooltip_line(3, tournament.rounds),
        ]

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        # Round 1: Group A gets 1 vpoint
        # Round 2: Group A gets 1 vpoint, Group B gets .5 vpoints
        if at_round <= 2:
            group = cls.get_player_group(tournament, player)
            if group == AccelerationGroup.A:
                return Result.WIN.points(tournament.point_values)
            elif at_round == 2:
                return Result.DRAW.points(tournament.point_values)
        return 0.0

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= 2


class ProgressiveSwissVariation(Acceleration3GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'PROGRESSIVE'

    @staticmethod
    def static_name() -> str:
        return _('Progressive accelerated system')

    @classmethod
    def _get_group_a_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return [
            cls._round_range_tooltip_line(
                1,
                tournament.rounds - 2,
                2 * Result.WIN.points(tournament.point_values),
            ),
            cls._round_range_tooltip_line(tournament.rounds - 1, tournament.rounds),
        ]

    @classmethod
    def _get_detailed_group_tooltip_lines(
        cls, tournament: Tournament, group: AccelerationGroup
    ) -> list[str]:
        draw_points = Result.DRAW.points(tournament.point_values)
        win_points = Result.WIN.points(tournament.point_values)
        get_vpoints = partial(
            cls._compute_virtual_points,
            group=group,
            tournament_rounds=tournament.rounds,
            draw_points=draw_points,
            win_points=win_points,
        )
        message = cls._get_incremental_points_message(
            get_vpoints, draw_points, 2 * win_points
        )
        return [
            cls._round_range_tooltip_line(
                1,
                tournament.rounds - 2,
                message=message,
            ),
            cls._round_range_tooltip_line(tournament.rounds - 1, tournament.rounds),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.B)

    @classmethod
    def _get_group_c_tooltip_lines(cls, tournament: Tournament) -> list[str]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.C)

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
            group=cls.get_player_group(tournament, player),
            tournament_rounds=tournament.rounds,
            points=player.points_before(at_round),
            draw_points=Result.DRAW.points(tournament.point_values),
            win_points=Result.WIN.points(tournament.point_values),
        )

    @staticmethod
    @cache
    def _compute_virtual_points(
        points: float,
        group: AccelerationGroup,
        tournament_rounds: int,
        draw_points: float,
        win_points: float,
    ) -> float:
        if 2 * points >= tournament_rounds * win_points:
            # If a player gets at least half the possible score,
            # their capital is set at 2 points.
            return 2 * win_points

        # Players get a virtual draw points for 3 real draw points
        vpoints = draw_points * (points // (3 * draw_points))

        # Starting points: Group A - 2, Group B - 1, Group C - 0
        match group:
            case AccelerationGroup.A:
                vpoints += 2 * win_points
            case AccelerationGroup.B:
                vpoints += win_points

        # Players cannot have more than 2 virtual points
        return min(2 * win_points, vpoints)

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= rounds - 2
