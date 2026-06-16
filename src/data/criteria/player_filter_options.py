from abc import ABC, abstractmethod
from collections import Counter
from types import UnionType
from typing import Any, TYPE_CHECKING

from common.exception import OptionError
from common.i18n import _
from common.i18n.utils import normalized_key, by
from common.sharly_chess_config import SharlyChessConfig
from data.player import TournamentPlayer
from data.player_categories import PlayerCategory, NoCategory
from utils.enum import PlayerGender, PlayerRatingType
from utils.option import Option

if TYPE_CHECKING:
    from data.tournament import Tournament
    from web.utils import SelectOption


class PlayerFilterOption(Option, ABC):
    """Parent class of all the options of player filters."""

    @property
    def template_name(self) -> str:
        return f'/admin/common/criteria/player_filter_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        """Name of the file of the template representing the option."""
        return self.id.lower()


class ExcludeFilterOption(PlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'EXCLUDE'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False


class SelectPlayerFilterOption[T](PlayerFilterOption):
    @abstractmethod
    def get_all_known_values(self, tournament: 'Tournament') -> list[T]:
        """All the known values of type [T] for the tournament."""

    @abstractmethod
    def get_tournament_player_counter(self, tournament: 'Tournament') -> Counter[T]:
        """The number of tournament players per object of type [T] in the tournament."""

    @abstractmethod
    def get_key(self, object_: T) -> str:
        """Get the key of the select option from an object of type [T]."""

    @abstractmethod
    def get_name(self, object_: T) -> str:
        """Get the name of the select option from an object of type [T]."""

    def get_tooltip(self, object_: T) -> str | None:
        """Get a tooltip to display on the option."""
        return None

    def get_search(self, object_: T) -> str | None:
        """Get a search string for an object's select option."""
        return None

    def select_options(
        self,
        tournament: 'Tournament',
        split_tournament_others: bool = True,
        include_unknown: bool = True,
    ) -> dict[str, 'SelectOption'] | dict[str, dict[str, 'SelectOption']]:
        """Build the select options for the tournament *tournament*.
        If *split_tournament_others*, the options will be split into 2 option groups:
            - one with the options matching players in the tournament, including the player count
            - the other with all the other possible values
        If *include_unknown*, tournament values will be added
        to the existing options if they don't already exist."""
        from web.utils import SelectOption

        tournament_player_counter = self.get_tournament_player_counter(tournament)
        all_values = self.get_all_known_values(tournament)
        if split_tournament_others:
            ordered_counters = sorted(
                tournament_player_counter.items(), key=lambda item: (-item[1], item[0])
            )
        else:
            ordered_counters = list(tournament_player_counter.items())
        tournament_options = {
            self.get_key(object_): SelectOption(
                f'{self.get_name(object_)} ({player_count})',
                self.get_tooltip(object_),
                search=self.get_search(object_),
            )
            for object_, player_count in ordered_counters
        }
        all_options = {
            self.get_key(object_): SelectOption(
                self.get_name(object_),
                self.get_tooltip(object_),
                search=self.get_search(object_),
            )
            for object_ in all_values
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
        return str

    @property
    def default_value(self) -> Any:
        return PlayerGender.WOMAN.value

    @property
    def template_file_name(self) -> str:
        return 'gender'

    def get_all_known_values(self, tournament: 'Tournament') -> list[PlayerGender]:
        return [gender for gender in PlayerGender if gender != PlayerGender.NONE]

    def get_tournament_player_counter(
        self, tournament: 'Tournament'
    ) -> Counter[PlayerGender]:
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


class AgeCategoryOption(SelectPlayerFilterOption[PlayerCategory], ABC):
    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        return None

    def get_tournament_player_counter(
        self, tournament: 'Tournament'
    ) -> Counter[PlayerCategory]:
        counter = tournament.category_counts
        if NoCategory() in counter:
            del counter[NoCategory()]
        return counter

    def age_select_options(
        self,
        tournament: 'Tournament',
    ) -> dict[str, 'SelectOption'] | dict[str, dict[str, 'SelectOption']]:
        from web.utils import SelectOption

        options = super().select_options(tournament, False, False)
        return {'': SelectOption('-')} | options  # type: ignore

    def get_all_known_values(self, tournament: 'Tournament') -> list[PlayerCategory]:
        categories = tournament.event.player_categories.copy()
        categories.pop(0)
        return categories

    def get_key(self, object_: PlayerCategory) -> str:
        return object_.id

    def get_name(self, object_: PlayerCategory) -> str:
        return object_.name

    def validate(self):
        super().validate()
        if self.value:
            try:
                PlayerCategory.from_id(self.value)
            except ValueError:
                raise OptionError(f'Unknown category [{self.value}]', self)


class MinAgeCategoryOption(AgeCategoryOption):
    @staticmethod
    def static_id() -> str:
        return 'MIN_AGE_CATEGORY'


class MaxAgeCategoryOption(AgeCategoryOption):
    @staticmethod
    def static_id() -> str:
        return 'MAX_AGE_CATEGORY'


class RatingTypesFilterOption(SelectPlayerFilterOption[PlayerRatingType]):
    @staticmethod
    def static_id() -> str:
        return 'RATING_TYPES'

    @property
    def type(self) -> type | UnionType:
        return list[int]

    @property
    def default_value(self) -> Any:
        return []

    def get_tournament_player_counter(
        self, tournament: 'Tournament'
    ) -> Counter[PlayerRatingType]:
        return tournament.rating_type_counts

    def get_all_known_values(self, tournament: 'Tournament') -> list[PlayerRatingType]:
        return [rating_type for rating_type in PlayerRatingType]

    def get_key(self, object_: PlayerRatingType) -> str:
        return str(object_.value)

    def get_name(self, object_: PlayerRatingType) -> str:
        return object_.name

    def validate(self):
        self._validate_list_type(int)
        if not self.value:
            raise OptionError(_('At least one value is expected.'), self)
        for rating_type in self.value:
            try:
                PlayerRatingType(rating_type)
            except ValueError:
                raise OptionError(f'Unknown rating_type [{rating_type}]', self)


class ClubsFilterOption(SelectPlayerFilterOption[str]):
    @staticmethod
    def static_id() -> str:
        return 'CLUBS'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[str]:
        event_club_names = {player.club.name for player in tournament.event.players}
        return [name for name in sorted(event_club_names, key=normalized_key) if name]

    def get_tournament_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        return tournament.club_counts

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        return object_

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one value is expected.'), self)


class FederationsFilterOption(SelectPlayerFilterOption[str]):
    @staticmethod
    def static_id() -> str:
        return 'FEDERATIONS'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[str]:
        return list(SharlyChessConfig().federations.keys())

    def get_tournament_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        return tournament.federation_counts

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        code = object_
        federations: dict[str, str] = SharlyChessConfig().federations
        if code not in federations:
            return code
        return f'{code} - {federations[code]}'

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one value is expected.'), self)


class CommentsFilterOption(SelectPlayerFilterOption[str]):
    @staticmethod
    def static_id() -> str:
        return 'COMMENTS'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[str]:
        return list(
            {player.comment for player in tournament.event.players if player.comment}
        )

    def get_tournament_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        counter = Counter[str]()
        for player in tournament.tournament_players:
            if player.comment:
                counter[player.comment] += 1
        return counter

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        return object_

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one value is expected.'), self)


class PlayersFilterOption(SelectPlayerFilterOption[TournamentPlayer]):
    @staticmethod
    def static_id() -> str:
        return 'PLAYERS'

    @property
    def type(self) -> type | UnionType:
        return list[int]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[TournamentPlayer]:
        return sorted(tournament.tournament_players, key=by('full_name'))

    def get_tournament_player_counter(
        self, tournament: 'Tournament'
    ) -> Counter[TournamentPlayer]:
        return Counter[TournamentPlayer]()

    def get_key(self, object_: TournamentPlayer) -> str:
        return str(object_.id)

    def get_name(self, object_: TournamentPlayer) -> str:
        return object_.full_name

    def validate(self):
        self._validate_list_type(int)
        if not self.value:
            raise OptionError(_('At least one player is expected.'), self)
