from abc import ABC, abstractmethod
from collections import Counter
from types import UnionType
from typing import Any, TYPE_CHECKING

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.player import Club, Federation
from utils.enum import PlayerGender, PlayerCategory
from utils.option import Option, OptionError

if TYPE_CHECKING:
    from data.tournament import Tournament


class PlayerFilterOption(Option, ABC):
    """Parent class of all the option of player filters."""

    @property
    def template_name(self) -> str:
        return f'player_filter_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        """Name of the file of the template representing the option."""
        return self.id.lower()


class SelectPlayerFilterOption[T](PlayerFilterOption):
    @abstractmethod
    def get_all_known_values(self, tournament: 'Tournament') -> list[T]:
        """All the known values of type [T] for the tournament."""

    @abstractmethod
    def get_player_counter(self, tournament: 'Tournament') -> Counter[T]:
        """The number of players per object of type [T] in the tournament."""

    @abstractmethod
    def get_key(self, object_: T) -> str:
        """Get the key of the select option from an object of type [T]."""

    @abstractmethod
    def get_name(self, object_: T) -> str:
        """Get the name of the select option from an object of type [T]."""

    def select_options(
        self,
        tournament: 'Tournament',
        split_tournament_others: bool = True,
        include_unknown: bool = True,
    ) -> dict[str, str] | dict[str, dict[str, str]]:
        """Build the select options for the tournament *tournament*.
        If *split_tournament_others*, the options will be split into 2 option groups:
            - one with the options matching players in the tournament, including the player count
            - the other with all the other possible values
        If *include_unknown*, tournament values will be added
        to the existing options if they don't already exist."""

        player_counter = self.get_player_counter(tournament)
        all_values = self.get_all_known_values(tournament)
        if split_tournament_others:
            ordered_counters = sorted(
                player_counter.items(), key=lambda item: (-item[1], item[0])
            )
        else:
            ordered_counters = list(player_counter.items())
        tournament_options = {
            self.get_key(object_): f'{self.get_name(object_)} ({player_count})'
            for object_, player_count in ordered_counters
        }
        all_options = {
            self.get_key(object_): self.get_name(object_) for object_ in all_values
        }
        if split_tournament_others:
            other_options = {
                key: name
                for key, name in all_options.items()
                if key not in tournament_options
            }
            if not tournament_options or not other_options:
                return other_options | tournament_options
            return {
                _('In-tournament'): tournament_options,
                _('Others'): other_options,
            }
        for key, name in tournament_options.items():
            if key in all_options or include_unknown:
                all_options[key] = name
        return all_options


class GenderOption(SelectPlayerFilterOption[PlayerGender]):
    @staticmethod
    def static_id() -> str:
        return 'GENDER_VALUE'

    @property
    def type(self) -> type | UnionType:
        return int

    @property
    def default_value(self) -> Any:
        return PlayerGender.FEMALE.value

    @property
    def template_file_name(self) -> str:
        return 'gender'

    def get_all_known_values(self, tournament: 'Tournament') -> list[PlayerGender]:
        return [gender for gender in PlayerGender if gender != PlayerGender.NONE]

    def get_player_counter(self, tournament: 'Tournament') -> Counter[PlayerGender]:
        return tournament.gender_counts

    def get_key(self, object_: PlayerGender) -> str:
        return str(object_.value)

    def get_name(self, object_: PlayerGender) -> str:
        return object_.name

    def validate(self):
        super().validate()
        try:
            PlayerGender(self.value)
        except ValueError:
            raise OptionError(f'Invalid gender value: {self.value}', self)


class RatingPlayerFilterOption(PlayerFilterOption, ABC):
    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    def validate(self):
        super().validate()
        if self.value and self.value < 0:
            raise OptionError(_('A positive integer is expected.'), self)


class MinRatingOption(RatingPlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'MIN_RATING'


class MaxRatingOption(RatingPlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'MAX_RATING'


class AgeCategoriesOption(SelectPlayerFilterOption[PlayerCategory]):
    @staticmethod
    def static_id() -> str:
        return 'AGE_CATEGORIES'

    @property
    def type(self) -> type | UnionType:
        return list[int]

    @property
    def default_value(self) -> Any:
        return []

    def get_player_counter(self, tournament: 'Tournament') -> Counter[PlayerCategory]:
        return tournament.category_counts

    def get_all_known_values(self, tournament: 'Tournament') -> list[PlayerCategory]:
        return [
            category for category in PlayerCategory if category != PlayerCategory.NONE
        ]

    def get_key(self, object_: PlayerCategory) -> str:
        return str(object_.value)

    def get_name(self, object_: PlayerCategory) -> str:
        return object_.short_name

    def validate(self):
        self._validate_list_type(int)
        if not self.value:
            raise OptionError(_('At least one age category is expected.'), self)
        for category in self.value:
            try:
                PlayerCategory(category)
            except ValueError:
                raise OptionError(f'Unknown category [{category}]', self)


class AgeRangePlayerFilterOption(PlayerFilterOption, ABC):
    @property
    @abstractmethod
    def field_placeholder(self) -> str:
        """Placeholder of the input field."""

    @property
    @abstractmethod
    def other_field_id(self) -> str:
        """ID of the other range field."""

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def template_file_name(self) -> str:
        return 'age_range'


class AgeLowerOption(AgeRangePlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'AGE_LOWER'

    @property
    def field_placeholder(self) -> str:
        return _('Include lower categories')

    @property
    def other_field_id(self) -> str:
        return AgeGreaterOption.static_id()


class AgeGreaterOption(AgeRangePlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'AGE_GREATER'

    @property
    def field_placeholder(self) -> str:
        return _('Include greater categories')

    @property
    def other_field_id(self) -> str:
        return AgeLowerOption.static_id()


class ClubsFilterOption(SelectPlayerFilterOption[Club]):
    @staticmethod
    def static_id() -> str:
        return 'CLUBS'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[Club]:
        return []

    def get_player_counter(self, tournament: 'Tournament') -> Counter[Club]:
        counter = tournament.club_counts
        empty_club = Club('')
        if empty_club in counter:
            counter.pop(empty_club)
        return counter

    def get_key(self, object_: Club) -> str:
        return object_.to_query_param

    def get_name(self, object_: Club) -> str:
        return object_.name

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one club is expected.'), self)


class FederationsFilterOption(SelectPlayerFilterOption[Federation]):
    @staticmethod
    def static_id() -> str:
        return 'FEDERATIONS'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[Federation]:
        return [Federation(code) for code in SharlyChessConfig.federations.keys()]

    def get_player_counter(self, tournament: 'Tournament') -> Counter[Federation]:
        counter = tournament.federation_counts
        empty_federation = Federation('')
        if empty_federation in counter:
            counter.pop(empty_federation)
        return counter

    def get_key(self, object_: Federation) -> str:
        return object_.to_query_param

    def get_name(self, object_: Federation) -> str:
        code = object_.name
        if code not in SharlyChessConfig.federations:
            return code
        return f'{code} - {SharlyChessConfig.federations[code]}'

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one federation is expected.'), self)
