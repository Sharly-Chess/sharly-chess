from abc import ABC, abstractmethod
from copy import copy
from functools import cache, partial
from math import ceil
from typing import Callable, Iterable

from common.i18n import _
from data.pairings.settings import PairingSetting
from data.pairings.variations import SwissVariation
from data.player import TournamentPlayer
from data.tournament import Tournament
from plugins.pairing_acceleration import PLUGIN_NAME
from plugins.pairing_acceleration.pairing_settings import (
    AccelerationGroup,
    GroupA2GroupsSetting,
    GroupB2GroupsSetting,
    GroupA3GroupsSetting,
    GroupB3GroupsSetting,
    GroupC3GroupsSetting,
    AccelerationRule,
)
from utils import Utils


class AccelerationSwissVariation(SwissVariation, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-{super().static_id()}'

    @abstractmethod
    def get_tournament_accelerated_rules(
        self, rounds: int, draw_points: float, win_points: float
    ) -> list[AccelerationRule]: ...

    @property
    def include_accelerated_rules_in_trf(self) -> bool:
        return True

    @property
    def vpoints_use_pairing_numbers(self) -> bool:
        return True

    @property
    def are_groups_editable(self) -> bool:
        """Defines if the pairing groups can be edited."""
        return True

    @classmethod
    @abstractmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        """Tooltip representing the group A."""

    @classmethod
    @abstractmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        """Tooltip representing the group B."""

    @classmethod
    def get_group_a_tooltip(cls, tournament: Tournament) -> str:
        return cls._build_tooltip(cls._get_group_a_tooltip_lines(tournament))

    @classmethod
    def get_group_b_tooltip(cls, tournament: Tournament) -> str:
        return cls._build_tooltip(cls._get_group_b_tooltip_lines(tournament))

    @staticmethod
    def _build_tooltip(tooltip_lines: list[tuple[str, float | None]]) -> str:
        if not tooltip_lines:
            return _('No acceleration.')
        return (
            f'<h6>{_("Virtual points")}</h6>'
            '<div '
            '   class="gap-0 d-grid align-self-center" '
            '   style="grid-template-columns: min-content min-content;"'
            '>'
            + ''.join(
                f'<div class="text-start text-nowrap">{prefix}</div>'
                f'<div class="text-start text-nowrap ps-1">'
                f'  {"→ " + Utils.points_str(points) if points is not None else ""}'
                f'</div>'
                for prefix, points in tooltip_lines
            )
            + '</div>'
        )

    @staticmethod
    def _rounds_prefix(
        min_round: int,
        max_round: int | None = None,
    ) -> str:
        if not max_round or min_round >= max_round:
            return _('Round {round}').format(round=min_round)
        else:
            return _('Rounds {min_round}-{max_round}').format(
                min_round=min_round, max_round=max_round
            )

    @classmethod
    @abstractmethod
    def get_player_group(
        cls, tournament: Tournament, tournament_player: TournamentPlayer
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
        cls, tournament: Tournament, tournament_player: TournamentPlayer
    ) -> AccelerationGroup:
        _, group_a_max = tournament.pairing_settings[GroupA2GroupsSetting.static_id()]
        if tournament_player.pairing_number <= group_a_max:
            return AccelerationGroup.A
        return AccelerationGroup.B

    def update_settings_from_deleted_pairing_numbers(
        self,
        tournament: 'Tournament',
        pairing_numbers: Iterable[int],
    ) -> bool:
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA2GroupsSetting.get_value(tournament)[1]
        new_max_a = max_a
        for pairing_number in pairing_numbers:
            if pairing_number <= max_a:
                new_max_a -= 1
        previous_pairing_settings = copy(tournament.stored_tournament.pairing_settings)
        tournament.stored_tournament.pairing_settings |= {
            GroupA2GroupsSetting().id: (1, new_max_a),
            GroupB2GroupsSetting().id: (new_max_a + 1, tournament.player_count),
        }
        return (
            previous_pairing_settings != tournament.stored_tournament.pairing_settings
        )

    def update_settings_from_added_pairing_number(
        self, tournament: 'Tournament', pairing_number: int
    ):
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA2GroupsSetting.get_value(tournament)[1]
        if pairing_number <= max_a:
            max_a += 1
        tournament.stored_tournament.pairing_settings |= {
            GroupA2GroupsSetting().id: (1, max_a),
            GroupB2GroupsSetting().id: (max_a + 1, tournament.player_count),
        }
        return True

    @classmethod
    def get_acceleration_group_max_numbers(cls, tournament: Tournament) -> list[int]:
        _, group_a_max = tournament.pairing_settings[GroupA2GroupsSetting().id]
        return [
            group_a_max,
        ]

    @classmethod
    def get_acceleration_number_range_by_group(
        cls, tournament: Tournament
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        return {
            AccelerationGroup.A: tournament.pairing_settings[GroupA2GroupsSetting().id],
            AccelerationGroup.B: tournament.pairing_settings[GroupB2GroupsSetting().id],
        }


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
    def _get_group_c_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        """Tooltip representing the group C."""

    @classmethod
    def get_group_c_tooltip(cls, tournament: Tournament) -> str:
        return cls._build_tooltip(cls._get_group_c_tooltip_lines(tournament))

    @classmethod
    def get_player_group(
        cls, tournament: Tournament, tournament_player: TournamentPlayer
    ) -> AccelerationGroup:
        _, group_a_max = tournament.pairing_settings[GroupA3GroupsSetting.static_id()]
        if tournament_player.pairing_number <= group_a_max:
            return AccelerationGroup.A
        _, group_b_max = tournament.pairing_settings[GroupB3GroupsSetting.static_id()]
        if tournament_player.pairing_number <= group_b_max:
            return AccelerationGroup.B
        return AccelerationGroup.C

    def update_settings_from_deleted_pairing_numbers(
        self,
        tournament: 'Tournament',
        pairing_numbers: Iterable[int],
    ) -> bool:
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA3GroupsSetting.get_value(tournament)[1]
        max_b = GroupB3GroupsSetting.get_value(tournament)[1]
        new_max_a = max_a
        new_max_b = max_b
        for pairing_number in pairing_numbers:
            if pairing_number <= max_a:
                new_max_a -= 1
            if pairing_number <= max_b:
                new_max_b -= 1
        previous_pairing_settings = copy(tournament.stored_tournament.pairing_settings)
        tournament.stored_tournament.pairing_settings |= {
            GroupA3GroupsSetting().id: (1, new_max_a),
            GroupB3GroupsSetting().id: (new_max_a + 1, new_max_b),
            GroupC3GroupsSetting().id: (new_max_b + 1, tournament.player_count),
        }
        return (
            previous_pairing_settings != tournament.stored_tournament.pairing_settings
        )

    def update_settings_from_added_pairing_number(
        self, tournament: 'Tournament', pairing_number: int
    ):
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA3GroupsSetting.get_value(tournament)[1]
        max_b = GroupB3GroupsSetting.get_value(tournament)[1]
        if pairing_number <= max_a:
            max_a += 1
        if pairing_number <= max_b:
            max_b += 1
        tournament.stored_tournament.pairing_settings |= {
            GroupA3GroupsSetting().id: (1, max_a),
            GroupB3GroupsSetting().id: (max_a + 1, max_b),
            GroupC3GroupsSetting().id: (max_b + 1, tournament.player_count),
        }
        return True

    @classmethod
    def get_acceleration_group_max_numbers(cls, tournament: Tournament) -> list[int]:
        _, group_a_max = tournament.pairing_settings[GroupA3GroupsSetting.static_id()]
        _, group_b_max = tournament.pairing_settings[GroupB3GroupsSetting.static_id()]
        return [
            group_a_max,
            group_b_max,
        ]

    @classmethod
    def get_acceleration_number_range_by_group(
        cls, tournament: Tournament
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        return {
            AccelerationGroup.A: tournament.pairing_settings[GroupA3GroupsSetting().id],
            AccelerationGroup.B: tournament.pairing_settings[GroupB3GroupsSetting().id],
            AccelerationGroup.C: tournament.pairing_settings[GroupC3GroupsSetting().id],
        }

    @staticmethod
    def _format_vpoints_inequality(
        min_points: float | None = None,
        max_points: float | None = None,
    ) -> str:
        points_name = _('points')
        min_str = Utils.points_str(min_points)
        max_str = Utils.points_str(max_points)
        if not min_points:
            inequality = f'{points_name} < {max_str}'
        elif not max_points:
            inequality = f'{points_name} ≥ {min_str}'
        else:
            inequality = f'{min_str} ≤ {points_name} < {max_str}'
        return '&nbsp;' * 4 + inequality

    @classmethod
    def _get_incremental_points_lines(
        cls,
        get_vpoints: Callable[[float], float],
        step: float,
        max_vpoints: float,
    ) -> list[tuple[str, float | None]]:
        message_lines: list[tuple[str, float | None]] = []
        points = 0.0
        previous_threshold: float | None = None
        previous_vpoints = get_vpoints(points)
        vpoints = previous_vpoints
        while vpoints < max_vpoints:
            points += step
            vpoints = get_vpoints(points)
            if previous_vpoints != vpoints:
                message_lines.append(
                    (
                        cls._format_vpoints_inequality(previous_threshold, points),
                        previous_vpoints,
                    )
                )
                previous_threshold = points
                previous_vpoints = vpoints

        message_lines.append(
            (
                cls._format_vpoints_inequality(points),
                vpoints,
            )
        )
        return message_lines


class BakuSwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'BAKU'

    @staticmethod
    def static_name():
        return _('Baku acceleration system')

    @property
    def trf_encoded_type(self) -> str:
        return 'FIDE_DUTCH_2026_BAKU'

    @property
    def include_accelerated_rules_in_trf(self) -> bool:
        # Acceleration already defined by the encoded type
        return False

    @property
    def are_groups_editable(self) -> bool:
        return False

    @classmethod
    def print_real_points(cls, current_round, rounds):
        return current_round <= cls.accelerated_rounds(rounds)

    @staticmethod
    def accelerated_rounds(rounds: int) -> int:
        return ceil(rounds / 2)

    @classmethod
    def full_point_rounds(cls, rounds: int) -> int:
        return ceil(cls.accelerated_rounds(rounds) / 2)

    @classmethod
    def compute_virtual_points(
        cls, tournament: Tournament, tournament_player: TournamentPlayer, at_round: int
    ) -> float:
        if at_round > cls.accelerated_rounds(tournament.rounds):
            return 0
        rating_group = cls.get_player_group(tournament, tournament_player)
        if at_round > cls.full_point_rounds(tournament.rounds):
            if rating_group == AccelerationGroup.A:
                return tournament.draw_points
            else:
                return 0
        else:
            if rating_group == AccelerationGroup.A:
                return tournament.win_points
            else:
                return 0

    def get_tournament_accelerated_rules(
        self, rounds: int, draw_points: float, win_points: float
    ) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=win_points,
                first_round=1,
                last_round=self.full_point_rounds(rounds),
                group=AccelerationGroup.A,
            ),
            AccelerationRule(
                vpoints=draw_points,
                first_round=self.full_point_rounds(rounds) + 1,
                last_round=self.accelerated_rounds(rounds),
                group=AccelerationGroup.A,
            ),
        ]

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        draw_points = tournament.draw_points
        rounds = tournament.rounds
        win_max_rounds = cls.full_point_rounds(rounds)
        draw_max_rounds = cls.accelerated_rounds(rounds)
        return [
            (cls._rounds_prefix(1, win_max_rounds), win_points),
            (cls._rounds_prefix(win_max_rounds + 1, draw_max_rounds), draw_points),
            (cls._rounds_prefix(draw_max_rounds + 1, rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        return []


class HaleySwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY'

    @staticmethod
    def static_name() -> str:
        return _('Haley system')

    def get_tournament_accelerated_rules(
        self, rounds: int, draw_points: float, win_points: float
    ) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=win_points,
                first_round=1,
                last_round=2,
                group=AccelerationGroup.A,
            ),
        ]

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        return [
            (cls._rounds_prefix(1, 2), win_points),
            (cls._rounds_prefix(3, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        return []

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        tournament_player: TournamentPlayer,
        at_round: int,
    ) -> float:
        if at_round <= 2:
            group = cls.get_player_group(tournament, tournament_player)
            if group == AccelerationGroup.A:
                return tournament.win_points
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

    def get_tournament_accelerated_rules(
        self, rounds: int, draw_points: float, win_points: float
    ) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=win_points,
                first_round=1,
                last_round=2,
                group=AccelerationGroup.A,
            ),
            AccelerationRule(
                vpoints=draw_points,
                first_round=2,
                last_round=2,
                group=AccelerationGroup.B,
            ),
        ]

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        return [
            (cls._rounds_prefix(1, 2), win_points),
            (cls._rounds_prefix(3, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        draw_points = tournament.draw_points
        return [
            (cls._rounds_prefix(1), 0),
            (cls._rounds_prefix(2), draw_points),
            (cls._rounds_prefix(3, tournament.rounds), 0),
        ]

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        tournament_player: TournamentPlayer,
        at_round: int,
    ) -> float:
        # Round 1: Group A gets 1 vpoint
        # Round 2: Group A gets 1 vpoint, Group B gets .5 vpoints
        if at_round <= 2:
            group = cls.get_player_group(tournament, tournament_player)
            if group == AccelerationGroup.A:
                return tournament.win_points
            elif at_round == 2:
                return tournament.draw_points
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

    def get_tournament_accelerated_rules(
        self, rounds: int, draw_points: float, win_points: float
    ) -> list[AccelerationRule]:
        rules: list[AccelerationRule] = []
        # Starting points: Group A - 2, Group B - 1, Group C - 0
        starting_vpoints_by_group = {
            AccelerationGroup.A: 2 * win_points,
            AccelerationGroup.B: win_points,
            AccelerationGroup.C: 0,
        }
        # Players cannot have more than 2 virtual points
        max_vpoints = 2 * win_points
        # If a player gets at least half the possible score,
        # their capital is set at 2 points.
        max_threshold = rounds * win_points / 2
        for group, starting_vpoints in starting_vpoints_by_group.items():
            threshold = 0.0
            vpoints = starting_vpoints
            while vpoints < max_vpoints and threshold < max_threshold:
                rule = AccelerationRule(
                    vpoints=vpoints,
                    first_round=1,
                    last_round=rounds - 2,
                    group=group,
                    points_threshold=threshold,
                )
                rules.append(rule)
                # Players get a virtual draw points for 3 real draw points
                threshold += 3 * draw_points
                vpoints += draw_points

            rule = AccelerationRule(
                vpoints=max_vpoints,
                first_round=1,
                last_round=rounds - 2,
                group=group,
                points_threshold=min(max_threshold, threshold),
            )
            rules.append(rule)
        return rules

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        return [
            (cls._rounds_prefix(1, tournament.rounds - 2), 2 * win_points),
            (cls._rounds_prefix(tournament.rounds - 1, tournament.rounds), 0),
        ]

    @classmethod
    def _get_detailed_group_tooltip_lines(
        cls, tournament: Tournament, group: AccelerationGroup
    ) -> list[tuple[str, float | None]]:
        draw_points = tournament.draw_points
        win_points = tournament.win_points
        get_vpoints = partial(
            cls._compute_virtual_points,
            group=group,
            tournament_rounds=tournament.rounds,
            draw_points=draw_points,
            win_points=win_points,
        )
        return [
            (cls._rounds_prefix(1, tournament.rounds - 2), None),
            *cls._get_incremental_points_lines(
                get_vpoints, draw_points, 2 * win_points
            ),
            (cls._rounds_prefix(tournament.rounds - 1, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.B)

    @classmethod
    def _get_group_c_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.C)

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        tournament_player: TournamentPlayer,
        at_round: int,
    ) -> float:
        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return 0.0
        return cls._compute_virtual_points(
            group=cls.get_player_group(tournament, tournament_player),
            tournament_rounds=tournament.rounds,
            points=tournament_player.points_before(at_round),
            draw_points=tournament.draw_points,
            win_points=tournament.win_points,
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
