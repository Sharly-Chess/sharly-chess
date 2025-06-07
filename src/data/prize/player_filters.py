from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cached_property

from common.i18n import _
from data.player import Player
from data.prize.player_filter_options import (
    PlayerFilterOption,
    GenderOption,
    MinRatingOption,
    MaxRatingOption,
    AgeCategoriesOption,
    AgeLowerOption,
    AgeGreaterOption,
)
from utils.enum import PlayerGender, PlayerCategory
from utils.option import OptionHandler, OptionError


class PlayerFilter(OptionHandler[PlayerFilterOption], ABC):
    """Abstract class representing ways to filter the players."""

    @abstractmethod
    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        """Return a function checking if a player is included in the filter or not."""

    @abstractmethod
    def __str__(self) -> str:
        """String representation of the filter."""


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
        return PlayerGender(self.get_option_values()[0])

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        gender = self.get_gender()
        return lambda player: player.gender == gender

    def __str__(self) -> str:
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
    def is_player_included_function(self) -> Callable[[Player], bool]:
        min_rating, max_rating = self.get_option_values()
        if not min_rating:
            return lambda player: player.rating <= max_rating
        if not max_rating:
            return lambda player: player.rating >= min_rating
        return lambda player: min_rating <= player.rating <= max_rating

    def __str__(self) -> str:
        min_rating, max_rating = self.get_option_values()
        if not min_rating:
            return f'{self.name} ≤ {max_rating}'
        if not max_rating:
            return f'{self.name} ≥ {min_rating}'
        return f'{min_rating} ≤ {self.name} ≤ {max_rating}'

    def validate_options(self):
        super().validate_options()
        min_rating, max_rating = self.get_option_values()
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
        return [AgeCategoriesOption, AgeLowerOption, AgeGreaterOption]

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        age_categories, lower, greater = self.get_option_values()
        categories = [PlayerCategory(category) for category in age_categories]
        if lower:
            category = categories[0]
            return lambda player: (
                player.category <= category and player.category != PlayerCategory.NONE
            )
        if greater:
            category = categories[0]
            return lambda player: player.category >= category
        return lambda player: player.category in categories

    def __str__(self) -> str:
        age_categories, lower, greater = self.get_option_values()
        categories = [
            PlayerCategory(category).short_name for category in age_categories
        ]
        if lower:
            return f'{self.name} ≤ {categories[0]}'
        if greater:
            return f'{self.name} ≥ {categories[0]}'
        return f'{self.name} ({", ".join(categories)})'

    def validate_options(self):
        super().validate_options()
        age_categories, lower, greater = self.get_option_values()
        if len(age_categories) > 1 and (lower or greater):
            raise OptionError(
                _(
                    'Only one age category is expected with options including other categories.'
                ),
                self._get_option(AgeCategoriesOption),
            )
        if lower and greater:
            raise OptionError(
                'Only one of greater or lower option is allowed.',
                self._get_option(AgeGreaterOption),
            )
