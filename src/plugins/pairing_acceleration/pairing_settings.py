from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings.settings import PairingSetting
from plugins.pairing_acceleration import PLUGIN_NAME

if TYPE_CHECKING:
    from data.tournament import Tournament


class AccelerationGroup(StrEnum):
    A = 'A'
    B = 'B'
    C = 'C'


@dataclass
class AccelerationRule:
    vpoints: float
    first_round: int
    last_round: int
    group: AccelerationGroup
    points_threshold: float = 0


class PairingGroupSetting(PairingSetting[tuple[int, int]], ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-GROUP_{cls.group()}_{cls.group_count()}'

    @classmethod
    def static_name(cls) -> str:
        return _('Group {group_id}').format(group_id=cls.group())

    @staticmethod
    @abstractmethod
    def group() -> AccelerationGroup:
        """The acceleration group matching the setting."""

    @staticmethod
    @abstractmethod
    def group_count() -> int:
        """Number of groups used in the settings group."""

    @classmethod
    @abstractmethod
    def default_values_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        """Compute the default values of each group."""

    @property
    def template_path(self) -> str:
        return f'/{PLUGIN_NAME}/group_{self.group().lower()}.html'

    @property
    def min_field(self) -> str:
        return f'{self.id}_min'

    @property
    def max_field(self) -> str:
        return f'{self.id}_max'

    def tooltip_representation(self, value: tuple[int, int]) -> str | None:
        return f'{value[0]} - {value[1]}'

    def from_form_data(self, data: dict[str, str]) -> tuple[int, int]:
        return (
            int(data[self.min_field]),
            int(data[self.max_field]),
        )

    def to_form_data(self, object_: tuple[int, int]) -> dict[str, str]:
        return {
            self.min_field: str(object_[0]),
            self.max_field: str(object_[1]),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field in (self.min_field, self.max_field):
            if not data.get(field, None) or int(data[field]) < 0:
                errors[self.id] = _('Positive values are expected.')
                return errors
        min_number, max_number = self.from_form_data(data)
        if min_number >= max_number:
            errors[self.id] = _('Maximum value must be greater than the minimum value.')
        return errors

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> tuple[int, int]:
        return cls.default_values_by_group(tournament)[cls.group()]

    @classmethod
    def check_value(cls, tournament: 'Tournament', value: tuple[int, int]) -> bool:
        return value[0] < value[1] <= tournament.player_count


class Base2GroupsSetting(PairingGroupSetting, ABC):
    @staticmethod
    def group_count() -> int:
        return 2

    @classmethod
    def default_values_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        player_count = tournament.player_count
        if player_count < 3:
            return {group: (0, 0) for group in AccelerationGroup}
        max_a = ceil(player_count / 4) * 2
        return {
            AccelerationGroup.A: (1, max_a),
            AccelerationGroup.B: (max_a + 1, player_count),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        if errors := super().get_data_errors(tournament, data):
            return errors

        min_number, max_number = self.from_form_data(data)
        if tournament.player_count / 4 > max_number - min_number + 1:
            return {
                self.id: _(
                    'Groups must be composed of at least 25%% of players.'
                ).replace('%%', '%')
            }
        return {}


class GroupA2GroupsSetting(Base2GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.A


class GroupB2GroupsSetting(Base2GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.B


class Base3GroupsSetting(PairingGroupSetting, ABC):
    @staticmethod
    def group_count() -> int:
        return 3

    @classmethod
    def default_values_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        """Recommended values for an ideal repartition of players.
        Ideal repartition:
            - Group A: closest multiple of 4 to a third of the players
            - Group B: closest multiple of 2 of half of the remaining players
            - Group C: remaining players"""
        player_count = len(tournament.tournament_players)
        if player_count < 3:
            return {group: (0, 0) for group in AccelerationGroup}
        if player_count < 11:
            # Min ideal repartition: A(4), B(4), C(3)
            max_a = player_count // 3
            max_b = 2 * player_count // 3
        else:
            max_a = 4 * round((player_count / 3) / 4)
            max_b = max_a + 2 * round((player_count - max_a) / 4)
        return {
            AccelerationGroup.A: (1, max_a),
            AccelerationGroup.B: (max_a + 1, max_b),
            AccelerationGroup.C: (max_b + 1, player_count),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        if errors := super().get_data_errors(tournament, data):
            return errors

        min_number, max_number = self.from_form_data(data)
        group_count = max_number - min_number + 1
        player_count = tournament.player_count
        if not player_count / 4 <= group_count <= player_count / 2:
            return {
                self.id: _(
                    'Groups must be composed of at least '
                    '25%% and at most 50%% of players.'
                ).replace('%%', '%')
            }
        return {}


class GroupA3GroupsSetting(Base3GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.A


class GroupB3GroupsSetting(Base3GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.B


class GroupC3GroupsSetting(Base3GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.C
