from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cached_property

from typing import TYPE_CHECKING

from common.exception import OptionError
from common.i18n import _
from common.i18n.utils import normalized_key
from data.player import TournamentPlayer
from data.criteria.player_filter_options import (
    PlayerFilterOption,
    GenderOption,
    MinRatingOption,
    MaxRatingOption,
    ClubsFilterOption,
    FederationsFilterOption,
    RatingTypesFilterOption,
    PlayersFilterOption,
    ExcludeFilterOption,
    CommentsFilterOption,
    MinAgeCategoryOption,
    MaxAgeCategoryOption,
)
from data.player_categories import NoCategory, PlayerCategory
from utils import Utils
from utils.enum import PlayerGender, PlayerRatingType
from utils.option import OptionHandler

if TYPE_CHECKING:
    from data.tournament import Tournament


class PlayerFilter(OptionHandler[PlayerFilterOption], ABC):
    """Abstract class representing ways to filter the players."""

    @abstractmethod
    def full_name(self, tournament: 'Tournament') -> str:
        """Full name of the filter, including the options."""

    @abstractmethod
    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        """Return a function checking if a player is included in the filter or not."""


class GenderPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'GENDER'

    @staticmethod
    def static_name() -> str:
        return _('Gender')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [GenderOption]

    def get_gender(self) -> PlayerGender:
        return PlayerGender(self._get_option(GenderOption).value)

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        gender = self.get_gender()
        return lambda player: player.gender == gender

    def full_name(self, tournament: 'Tournament') -> str:
        return _('Gender ({gender})').format(gender=self.get_gender().short_name)


class RatingPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'RATING'

    @staticmethod
    def static_name() -> str:
        return _('Rating')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [MinRatingOption, MaxRatingOption]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        min_rating = self._get_option(MinRatingOption).value
        max_rating = self._get_option(MaxRatingOption).value
        if not min_rating:
            # validate_options() rejects a filter with neither bound set.
            assert max_rating is not None
            return lambda player: player.rating <= max_rating
        if not max_rating:
            return lambda player: player.rating >= min_rating
        return lambda player: min_rating <= player.rating <= max_rating

    def full_name(self, tournament: 'Tournament') -> str:
        min_rating = self._get_option(MinRatingOption).value
        max_rating = self._get_option(MaxRatingOption).value
        return Utils.get_rating_range_label(min_rating, max_rating)

    def validate_options(self) -> None:
        super().validate_options()
        min_rating = self._get_option(MinRatingOption).value
        max_rating = self._get_option(MaxRatingOption).value
        if not min_rating and not max_rating:
            raise OptionError(
                _('At least a minimum or a maximum rating must be defined.'),
                self._get_option(MinRatingOption),
            )
        if min_rating and max_rating and max_rating < min_rating:
            raise OptionError(
                _('The maximum rating must be at most equal to the minimum rating.'),
                self._get_option(MaxRatingOption),
            )


class AgePlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'AGE'

    @staticmethod
    def static_name() -> str:
        return _('Age')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [MinAgeCategoryOption, MaxAgeCategoryOption]

    @property
    def category_range(self) -> tuple[PlayerCategory | None, PlayerCategory | None]:
        min_id = self._get_option(MinAgeCategoryOption).value
        max_id = self._get_option(MaxAgeCategoryOption).value
        return (
            PlayerCategory.from_id(min_id) if min_id else None,
            PlayerCategory.from_id(max_id) if max_id else None,
        )

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        min_category, max_category = self.category_range
        if not min_category:
            return lambda player: (
                player.category <= max_category and player.category != NoCategory()
            )
        if not max_category:
            return lambda player: (
                player.category >= min_category and player.category != NoCategory()
            )
        if max_category == min_category:
            return lambda player: player.category == max_category
        return lambda player: min_category <= player.category <= max_category

    def full_name(self, tournament: 'Tournament') -> str:
        min_category, max_category = self.category_range
        if not min_category:
            # One of the two is always set; only the other can be None here.
            assert max_category is not None
            return f'{self.name} ≤ {max_category.name}'
        if not max_category:
            return f'{self.name} ≥ {min_category.name}'
        if max_category == min_category:
            return f'{self.name} ({min_category.name})'
        return f'{min_category.name} ≤ {self.name} ≤ {max_category.name}'

    def validate_options(self) -> None:
        super().validate_options()
        min_category, max_category = self.category_range
        if not min_category and not max_category:
            raise OptionError(
                _('At least a minimum or a maximum category must be defined.'),
                self._get_option(MinAgeCategoryOption),
            )
        if min_category and max_category and min_category > max_category:
            raise OptionError(
                _(
                    'The maximum category must be at most equal to the minimum category.'
                ),
                self._get_option(MaxAgeCategoryOption),
            )


class RatingTypePlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'RATING_TYPE'

    @staticmethod
    def static_name() -> str:
        return _('Rating type')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [RatingTypesFilterOption]

    def get_rating_types(self) -> list[PlayerRatingType]:
        return [
            PlayerRatingType(rating_type)
            for rating_type in self._get_option(RatingTypesFilterOption).value
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        rating_types = self.get_rating_types()
        return lambda player: player.rating_type in rating_types

    def full_name(self, tournament: 'Tournament') -> str:
        option_str = ', '.join(
            rating_type.short_name for rating_type in self.get_rating_types()
        )
        return f'{self.name} ({option_str})'


class ClubPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'CLUB'

    @staticmethod
    def static_name() -> str:
        return _('Club')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            ClubsFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        clubs = self._get_option(ClubsFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        if exclude:
            return lambda player: player.club.name not in clubs
        return lambda player: player.club.name in clubs

    def full_name(self, tournament: 'Tournament') -> str:
        clubs = self._get_option(ClubsFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        option_str = ', '.join(clubs)
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'


class FederationPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'FEDERATION'

    @staticmethod
    def static_name() -> str:
        return _('Federation')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            FederationsFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        federations = self._get_option(FederationsFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        if exclude:
            return lambda player: player.federation.name not in federations
        return lambda player: player.federation.name in federations

    def full_name(self, tournament: 'Tournament') -> str:
        federations = self._get_option(FederationsFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        option_str = ', '.join(federations)
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'


class CommentPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'COMMENT'

    @staticmethod
    def static_name() -> str:
        return _('Comment')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            CommentsFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        comments = self._get_option(CommentsFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        if exclude:
            return lambda player: player.comment not in comments
        return lambda player: player.comment in comments

    def full_name(self, tournament: 'Tournament') -> str:
        comments = self._get_option(CommentsFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        option_str = ', '.join(comments)
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'


class PlayerIdPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return 'PLAYER'

    @staticmethod
    def static_name() -> str:
        return _('Players')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            PlayersFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        player_ids = self._get_option(PlayersFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        if exclude:
            return lambda player: player.id not in player_ids
        return lambda player: player.id in player_ids

    def full_name(self, tournament: 'Tournament') -> str:
        player_ids = self._get_option(PlayersFilterOption).value
        exclude = self._get_option(ExcludeFilterOption).value
        player_names = [
            player.full_name
            for player in tournament.tournament_players
            if player.id in player_ids
        ]
        option_str = ', '.join(sorted(player_names, key=normalized_key))
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'
