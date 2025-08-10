import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from common.i18n import _
from utils.entity import IdentifiableEntity
from utils.enum import BoardColor

if TYPE_CHECKING:
    from data.tournament import Tournament


class PairingSetting[T](IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def template_path(self) -> str:
        """Path of the template used to represent the field in the form."""

    @abstractmethod
    def tooltip_representation(self, value: T) -> str | None:
        """String representing the setting in the pairing tooltip
        located on the tournament card.
        Returns None if the setting should not be represented."""

    @abstractmethod
    def from_form_data(self, data: dict[str, str]) -> T:
        """Extract the setting value from the form data."""

    @abstractmethod
    def to_form_data(self, object_: T) -> dict[str, str]:
        """Convert the setting object to form data."""

    @abstractmethod
    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        """Check if one of the fields has an error."""

    @classmethod
    @abstractmethod
    def default_value(cls, tournament: 'Tournament') -> T:
        """Get the default value of the setting from the tournament."""

    @classmethod
    def from_stored_value(cls, value: Any) -> T:
        """Initialize a T object from the stored value."""
        return value

    @classmethod
    def to_stored_value(cls, object_: T) -> Any:
        """Create the value to store in the database from a T object."""
        return object_

    @classmethod
    def is_valid(cls, tournament: 'Tournament') -> bool:
        if not cls.is_set(tournament):
            return False
        assert tournament.pairing_settings is not None
        return cls.check_value(
            tournament,
            cls.from_stored_value(tournament.pairing_settings[cls.static_id()]),
        )

    @classmethod
    @abstractmethod
    def check_value(cls, tournament: 'Tournament', value: T) -> bool:
        """Check if a value of type T is valid for pairing generation for a tournament."""

    @classmethod
    def is_set(cls, tournament: 'Tournament'):
        """Check if the value is set in the stored settings."""
        settings = tournament.pairing_settings
        return settings and cls.static_id() in settings

    def default_form_data(self, tournament: 'Tournament') -> dict[str, str]:
        return self.to_form_data(self.default_value(tournament))

    def get_form_data(self, tournament: 'Tournament') -> dict[str, str]:
        if self.is_set(tournament):
            return self.to_form_data(self.get_value(tournament))
        return self.default_form_data(tournament)

    @classmethod
    def get_value(cls, tournament: 'Tournament') -> T:
        if tournament.pairing_settings and cls.is_set(tournament):
            value = cls.from_stored_value(tournament.pairing_settings[cls.static_id()])
            if cls.check_value(tournament, value):
                return value
        return cls.default_value(tournament)


class ColorSeedSetting(PairingSetting[BoardColor]):
    RANDOM_ID: str = 'R'

    @staticmethod
    def static_id() -> str:
        return 'COLOR_SEED'

    @staticmethod
    def static_name() -> str:
        return _('Seed color')

    @property
    def template_path(self) -> str:
        return '/admin/pairings/settings/color_seed.html'

    def tooltip_representation(self, value: BoardColor) -> str | None:
        return value.name

    def from_form_data(self, data: dict[str, str]) -> BoardColor:
        value = data[self.id]
        if value == self.RANDOM_ID:
            return random.choice([BoardColor.WHITE, BoardColor.BLACK])
        return BoardColor(data[self.id])

    def to_form_data(self, object_: BoardColor) -> dict[str, str]:
        return {self.id: object_.value}

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        return {}

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> BoardColor:
        return cls._computed_value(tournament) or BoardColor.WHITE

    @classmethod
    def _computed_value(cls, tournament: 'Tournament') -> BoardColor | None:
        return next(
            (
                player.pairings[1].color
                for player in sorted(
                    tournament.players,
                    key=lambda player: player.starting_rank_sort_key,
                    reverse=True,
                )
                if 1 in player.pairings and player.pairings[1].color is not None
            ),
            None,
        )

    @classmethod
    def from_stored_value(cls, value: Any) -> BoardColor:
        return BoardColor(value)

    @classmethod
    def to_stored_value(cls, object_: BoardColor) -> Any:
        return object_.value

    @classmethod
    def check_value(cls, tournament: 'Tournament', value: BoardColor):
        return True

    def default_form_data(self, tournament: 'Tournament') -> dict[str, str]:
        color = self._computed_value(tournament)
        return {self.id: color.value if color else ''}

    @property
    def options(self) -> dict[str, str]:
        return {
            self.RANDOM_ID: _('Random'),
            BoardColor.WHITE.value: BoardColor.WHITE.name,
            BoardColor.BLACK.value: BoardColor.BLACK.name,
        }


class BergerNumbersSetting(PairingSetting[dict[int, int]]):
    @staticmethod
    def static_id() -> str:
        return 'BERGER_NUMBERS'

    @staticmethod
    def static_name() -> str:
        return ''

    @property
    def template_path(self) -> str:
        return '/admin/pairings/settings/berger_numbers.html'

    def tooltip_representation(self, value: dict[int, int]) -> str | None:
        return None

    def from_form_data(self, data: dict[str, str]) -> dict[int, int]:
        return {
            int(field.replace(self.player_field_base, '')): int(data[field])
            for field in self._berger_number_fields(data)
        }

    def to_form_data(self, object_: dict[int, int]) -> dict[str, str]:
        return {
            self.player_field_base + str(player_id): str(pairing_number)
            for player_id, pairing_number in object_.items()
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        pairing_numbers: set[int] = set()
        for field in self._berger_number_fields(data):
            value = data[field]
            if not value or (int_value := int(value)) < 1:
                errors[field] = _('A positive integer is expected.')
            elif int_value > tournament.player_count:
                errors[field] = _(
                    "The pairing number can't be greater than the player count."
                )
            elif int_value in pairing_numbers:
                errors[field] = _('The pairing number is already attributed.')
            else:
                pairing_numbers.add(int_value)
        return errors

    @classmethod
    def from_stored_value(cls, value: Any) -> dict[int, int]:
        return {
            int(player_id): pairing_number
            for player_id, pairing_number in value.items()
        }

    @classmethod
    def to_stored_value(cls, object_: dict[int, int]) -> Any:
        return {
            str(player_id): pairing_number
            for player_id, pairing_number in object_.items()
        }

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> dict[int, int]:
        return {
            player.id: rank
            for rank, player in tournament.players_by_starting_rank.items()
        }

    @classmethod
    def check_value(cls, tournament: 'Tournament', value: dict[int, int]):
        berger_numbers = value
        for player in tournament.players:
            if player.id not in berger_numbers:
                return False
            if berger_numbers[player.id] > tournament.player_count:
                return False
        return True

    @property
    def player_field_base(self) -> str:
        """Base of the ID of the form field allowing to input the berger number
        of a player. The player ID is supposed to be concatenated to the base."""
        return 'berger_number_'

    def _berger_number_fields(self, data: dict[str, str]):
        return [
            field for field in data.keys() if field.startswith(self.player_field_base)
        ]
