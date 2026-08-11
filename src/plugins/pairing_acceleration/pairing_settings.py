from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from typing import TYPE_CHECKING, Any

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
    """Virtual points granted over a range of rounds, either to an
    acceleration group or, when *number_range* is set, to an explicit
    range of pairing numbers (one TRF26 250 record)."""

    vpoints: float
    first_round: int
    last_round: int
    group: AccelerationGroup | None = None
    points_threshold: float = 0
    number_range: tuple[int, int] | None = None


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


class CustomAccelerationSetting(PairingSetting[list[AccelerationRule]]):
    """The rules of the custom accelerated system, each one mapping to a
    TRF26 250 record: virtual points granted to a range of pairing
    numbers over a range of rounds.

    Form fields are indexed (``<id>_<index>_<field>``) so that rows can be
    added and removed client-side; the indexes only have to be distinct,
    not contiguous."""

    MAX_VPOINTS = 99.9

    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-CUSTOM_ACCELERATION'

    @staticmethod
    def static_name() -> str:
        return _('Accelerated rounds')

    @property
    def template_path(self) -> str:
        return f'/{PLUGIN_NAME}/custom_acceleration.html'

    def field(self, index: int, name: str) -> str:
        return f'{self.id}_{index}_{name}'

    def row_indexes(self, data: dict[str, str]) -> list[int]:
        prefix = f'{self.id}_'
        suffix = '_vpoints'
        indexes: set[int] = set()
        for key in data:
            if key.startswith(prefix) and key.endswith(suffix):
                index = key[len(prefix) : -len(suffix)]
                if index.isdigit():
                    indexes.add(int(index))
        return sorted(indexes)

    def tooltip_representation(self, value: list[AccelerationRule]) -> str | None:
        if not value:
            return None
        return str(len(value))

    def from_form_data(self, data: dict[str, str]) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=float(data[self.field(index, 'vpoints')]),
                first_round=int(data[self.field(index, 'first_round')]),
                last_round=int(data[self.field(index, 'last_round')]),
                number_range=(
                    int(data[self.field(index, 'first_number')]),
                    int(data[self.field(index, 'last_number')]),
                ),
            )
            for index in self.row_indexes(data)
        ]

    def to_form_data(self, object_: list[AccelerationRule]) -> dict[str, str]:
        data: dict[str, str] = {}
        for index, rule in enumerate(object_):
            first_number, last_number = rule.number_range or (1, 1)
            data |= {
                self.field(index, 'vpoints'): f'{rule.vpoints:g}',
                self.field(index, 'first_round'): str(rule.first_round),
                self.field(index, 'last_round'): str(rule.last_round),
                self.field(index, 'first_number'): str(first_number),
                self.field(index, 'last_number'): str(last_number),
            }
        return data

    @classmethod
    def to_stored_value(cls, object_: list[AccelerationRule]) -> Any:
        return [
            {
                'vpoints': rule.vpoints,
                'first_round': rule.first_round,
                'last_round': rule.last_round,
                'first_number': (rule.number_range or (1, 1))[0],
                'last_number': (rule.number_range or (1, 1))[1],
            }
            for rule in object_
        ]

    @classmethod
    def from_stored_value(cls, value: Any) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=float(rule['vpoints']),
                first_round=int(rule['first_round']),
                last_round=int(rule['last_round']),
                number_range=(int(rule['first_number']), int(rule['last_number'])),
            )
            for rule in value
        ]

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> list[AccelerationRule]:
        return []

    @classmethod
    def check_value(
        cls, tournament: 'Tournament', value: list[AccelerationRule]
    ) -> bool:
        covered: set[tuple[int, int]] = set()
        for rule in value:
            if rule.number_range is None:
                return False
            if not 0 <= rule.vpoints <= cls.MAX_VPOINTS:
                return False
            if not 1 <= rule.first_round <= rule.last_round <= tournament.rounds:
                return False
            first_number, last_number = rule.number_range
            if not 1 <= first_number <= last_number <= tournament.player_count:
                return False
            cells = cls._covered_cells(
                (rule.first_round, rule.last_round), rule.number_range
            )
            if cells & covered:
                return False
            covered |= cells
        return True

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        covered: set[tuple[int, int]] = set()
        for index in self.row_indexes(data):
            self._get_vpoints_errors(errors, data, index)
            round_range = self._get_range(
                errors,
                data,
                index,
                'round',
                tournament.rounds,
                _('A round between 1 and {max} is expected.').format(
                    max=tournament.rounds
                ),
            )
            number_range = self._get_range(
                errors,
                data,
                index,
                'number',
                tournament.player_count,
                _('A pairing number between 1 and {max} is expected.').format(
                    max=tournament.player_count
                ),
            )
            if round_range is None or number_range is None:
                continue
            cells = self._covered_cells(round_range, number_range)
            if overlap := cells & covered:
                round_, number = min(overlap)
                errors[self.field(index, 'first_number')] = _(
                    'Round {round} of pairing number {number} is already accelerated.'
                ).format(round=round_, number=number)
            covered |= cells
        return errors

    def _get_vpoints_errors(
        self, errors: dict[str, str], data: dict[str, str], index: int
    ):
        field = self.field(index, 'vpoints')
        vpoints = self._parse_float(data.get(field))
        if vpoints is None or not 0 <= vpoints <= self.MAX_VPOINTS:
            errors[field] = _('A value between 0 and {max} is expected.').format(
                max=f'{self.MAX_VPOINTS:g}'
            )
        elif round(vpoints * 10) != vpoints * 10:
            errors[field] = _('At most one decimal is expected.')

    def _get_range(
        self,
        errors: dict[str, str],
        data: dict[str, str],
        index: int,
        name: str,
        max_value: int,
        message: str,
    ) -> tuple[int, int] | None:
        first_field = self.field(index, f'first_{name}')
        last_field = self.field(index, f'last_{name}')
        first = self._parse_int(data.get(first_field))
        last = self._parse_int(data.get(last_field))
        for field, value in ((first_field, first), (last_field, last)):
            if value is None or not 1 <= value <= max_value:
                errors[field] = message
        if first_field in errors or last_field in errors:
            return None
        assert first is not None and last is not None
        if first > last:
            errors[last_field] = _('The end of the range must not precede its start.')
            return None
        return first, last

    @staticmethod
    def _covered_cells(
        round_range: tuple[int, int], number_range: tuple[int, int]
    ) -> set[tuple[int, int]]:
        """The (round, pairing number) pairs a rule accelerates, used to
        check that no two rules accelerate the same one."""
        return {
            (round_, number)
            for round_ in range(round_range[0], round_range[1] + 1)
            for number in range(number_range[0], number_range[1] + 1)
        }

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
