from abc import ABC, abstractmethod
from functools import cached_property
from typing import Any, Callable, TYPE_CHECKING

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.player import TournamentPlayer
from data.player_categories import PlayerCategory, NoCategory
from utils import Utils
from utils.entity import IdentifiableEntity
from utils.enum import PlayerGender
from web.controllers.base_controller import WebContext

if TYPE_CHECKING:
    from data.event import Event


class TournamentCriterion[T](IdentifiableEntity, ABC):
    def __init__(self, value: T | None = None):
        self._value = value

    @property
    def value(self) -> T:
        assert self._value is not None
        return self._value

    def set_value(self, value: T):
        self._value = value

    @property
    def form_key(self) -> str:
        return 'criteria_' + self.id

    @property
    def template_name(self) -> str:
        """Template of the criteria fields in the tournament form."""
        return f'/admin/tournaments/criteria/{self.id}.html'

    @property
    def full_name(self) -> str:
        """Full name of the criterion including the value."""
        return f'{self.name} ({self.value})'

    @property
    def stored_value(self) -> Any:
        """Value stored in the DB, must be serializable."""
        return self.value

    def value_from_stored_value(self, stored_value: Any) -> T:
        """Initialize a value from the stored value."""
        return stored_value

    @abstractmethod
    def value_from_form_data(
        self, data: dict[str, str], errors: dict[str, str]
    ) -> T | None:
        """Initialize the value from form data.
        Returns None if the criterion is not taken into account."""

    def add_to_form_data(self, data: dict[str, str]):
        """Add the value to the form data."""
        data[self.form_key] = WebContext.value_to_form_data(self._value)

    def is_used_in_form_data(self, data: dict[str, str]) -> bool:
        """Defines if the criteria is used in the form data."""
        return bool(data.get(self.form_key))

    @cached_property
    @abstractmethod
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        """Return a function checking if a player is included by the criteria or not."""


class GenderTournamentCriterion(TournamentCriterion[str]):
    @staticmethod
    def static_id() -> str:
        return 'gender'

    @staticmethod
    def static_name() -> str:
        return _('Gender')

    @property
    def full_name(self) -> str:
        return f'{self.name} ({PlayerGender(self.value).short_name})'

    def value_from_form_data(
        self, data: dict[str, str], errors: dict[str, str]
    ) -> str | None:
        value = WebContext.form_data_to_str(data, self.form_key)
        if value:
            try:
                PlayerGender(value)
                return value
            except ValueError:
                errors[self.form_key] = 'Unknown gender value [value]'
        return None

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        gender = PlayerGender(self.value)
        return lambda player: player.gender == gender

    @property
    def select_options(self) -> dict[str, str]:
        return {'': '-'} | {
            gender.value: gender.name
            for gender in [PlayerGender.MAN, PlayerGender.WOMAN]
        }


class RatingTournamentCriterion(TournamentCriterion[dict[str, int | None]]):
    @staticmethod
    def static_id() -> str:
        return 'rating'

    @staticmethod
    def static_name() -> str:
        return _('Rating')

    @property
    def rating_limits(self) -> tuple[int | None, int | None]:
        if not self._value:
            return None, None
        return self.value.get('min'), self.value.get('max')

    @property
    def full_name(self) -> str:
        min_rating, max_rating = self.rating_limits
        return Utils.get_rating_range_label(min_rating, max_rating)

    def value_from_form_data(
        self, data: dict[str, str], errors: dict[str, str]
    ) -> dict[str, int | None] | None:
        field = self.form_key
        try:
            min_rating = WebContext.form_data_to_int(data, field + '_min', minimum=0)
            max_rating = WebContext.form_data_to_int(data, field + '_max', minimum=0)
            if min_rating and max_rating and min_rating >= max_rating:
                errors[field] = _(
                    'Minimum rating is expected to be lower than the maximum rating.'
                )
            if min_rating or max_rating:
                return {'min': min_rating, 'max': max_rating}
            return None
        except ValueError:
            errors[field] = _('Positive values are expected.')
            return None

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        min_rating, max_rating = self.rating_limits
        if min_rating and max_rating:
            return lambda player: min_rating <= player.rating <= max_rating
        elif max_rating:
            return lambda player: player.rating <= max_rating
        else:
            assert min_rating is not None
            return lambda player: player.rating >= min_rating

    def add_to_form_data(self, data: dict[str, str]):
        min_rating, max_rating = self.rating_limits
        data[self.form_key + '_min'] = WebContext.value_to_form_data(min_rating)
        data[self.form_key + '_max'] = WebContext.value_to_form_data(max_rating)

    def is_used_in_form_data(self, data: dict[str, str]) -> bool:
        return bool(
            data.get(self.form_key + '_min') or data.get(self.form_key + '_max')
        )


class AgeCategoryTournamentCriterion(TournamentCriterion[dict[str, str | None]]):
    @staticmethod
    def static_id() -> str:
        return 'age_category'

    @staticmethod
    def static_name() -> str:
        return _('Category')

    @property
    def category_limits(self) -> tuple[PlayerCategory | None, PlayerCategory | None]:
        if not self._value:
            return None, None
        min_category: PlayerCategory | None = None
        max_category: PlayerCategory | None = None
        if min_id := self.value.get('min'):
            min_category = PlayerCategory.from_id(min_id)
        if max_id := self.value.get('max'):
            max_category = PlayerCategory.from_id(max_id)
        return min_category, max_category

    @property
    def full_name(self) -> str:
        min_category, max_category = self.category_limits
        if min_category and max_category:
            if min_category == max_category:
                return f'{self.name} ({min_category.name})'
            return f'{min_category.name} ≤ {self.name} ≤ {max_category.name}'
        elif max_category:
            return f'{self.name} ≤ {max_category.name}'
        elif min_category:
            assert min_category is not None
            return f'{self.name} ≥ {min_category.name}'
        return self.name

    def value_from_form_data(
        self, data: dict[str, str], errors: dict[str, str]
    ) -> dict[str, str | None] | None:
        field = self.form_key
        min_category: PlayerCategory | None = None
        max_category: PlayerCategory | None = None
        min_id = WebContext.form_data_to_str(data, field + '_min')
        max_id = WebContext.form_data_to_str(data, field + '_max')
        try:
            if min_id and min_id != '__placeholder__':
                min_category = PlayerCategory.from_id(min_id)
            if max_id and max_id != '__placeholder__':
                max_category = PlayerCategory.from_id(max_id)
        except ValueError:
            errors[field] = 'Unknown category ID.'

        if min_category and max_category and min_category > max_category:
            errors[field] = _(
                'Minimum category is expected to be lower or equal to the maximum category.'
            )
        if min_category or max_category:
            return {
                'min': getattr(min_category, 'id', None),
                'max': getattr(max_category, 'id', None),
            }
        return None

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        min_category, max_category = self.category_limits

        if min_category and max_category:
            if min_category == max_category:
                return lambda player: player.category == min_category
            return lambda player: min_category <= player.category <= max_category  # type: ignore
        elif max_category:
            return lambda player: (
                player.category <= max_category  # type: ignore
                and player.category != NoCategory()
            )
        else:
            assert min_category is not None
            return lambda player: (
                player.category >= min_category  # type: ignore
                and player.category != NoCategory()
            )

    def add_to_form_data(self, data: dict[str, str]):
        min_category, max_category = self.category_limits
        data[self.form_key + '_min'] = WebContext.value_to_form_data(
            getattr(min_category, 'id', None)
        )
        data[self.form_key + '_max'] = WebContext.value_to_form_data(
            getattr(max_category, 'id', None)
        )

    def is_used_in_form_data(self, data: dict[str, str]) -> bool:
        return bool(
            data.get(self.form_key + '_min') or data.get(self.form_key + '_max')
        )

    def get_select_options(self, event: 'Event') -> dict[str, str]:
        return {
            category.id: category.name
            for category in event.player_categories
            if category != NoCategory()
        }


class ClubTournamentCriterion(TournamentCriterion[str]):
    @staticmethod
    def static_id() -> str:
        return 'club'

    @staticmethod
    def static_name() -> str:
        return _('Club')

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        club = self.value
        return lambda player: player.club.name == club

    def value_from_form_data(
        self, data: dict[str, str], errors: dict[str, str]
    ) -> str | None:
        return WebContext.form_data_to_str(data, self.form_key)


class FederationTournamentCriterion(TournamentCriterion[str]):
    @staticmethod
    def static_id() -> str:
        return 'federation'

    @staticmethod
    def static_name() -> str:
        return _('Federation')

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        fed = self.value
        return lambda player: player.federation.name == fed

    def value_from_form_data(
        self, data: dict[str, str], errors: dict[str, str]
    ) -> str | None:
        return WebContext.form_data_to_str(data, self.form_key)

    @property
    def select_options(self) -> dict[str, str]:
        return {'': '-'} | {
            key: f'{key} - {name}'
            for key, name in SharlyChessConfig().federations.items()
            if key != 'NON'
        }
