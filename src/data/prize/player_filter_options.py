from abc import ABC, abstractmethod
from types import UnionType
from typing import Any

from common.i18n import _
from utils.enum import PlayerGender, PlayerCategory
from utils.option import Option, OptionError
from web.controllers.base_controller import WebContext


class PlayerFilterOption(Option, ABC):
    """Parent class of all the option of player filters."""

    @property
    def template_name(self) -> str:
        return f'player_filter_options/{self.template_file_name}.html'

    @property
    @abstractmethod
    def template_file_name(self) -> str:
        """Name of the file of the template representing the option."""


class GenderOption(PlayerFilterOption):
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

    @property
    def gender_options(self) -> dict[str, str]:
        return {
            WebContext.value_to_form_data(gender.value): gender.name
            for gender in PlayerGender
            if gender != PlayerGender.NONE
        }

    def validate(self):
        super().validate()
        try:
            PlayerGender(self.value)
        except ValueError:
            raise OptionError(f'Invalid gender value: {self.value}', self)


class RatingPlayerFilterOption(PlayerFilterOption, ABC):
    @property
    @abstractmethod
    def label(self) -> str:
        """Label of the input field."""

    @property
    @abstractmethod
    def help_text(self) -> str:
        """Help text of the input field."""

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def template_file_name(self) -> str:
        return 'rating'

    def validate(self):
        super().validate()
        if self.value and self.value < 0:
            raise OptionError(_('A positive integer is expected.'), self)


class MinRatingOption(RatingPlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'MIN_RATING'

    @property
    def label(self) -> str:
        return _('Minimum rating')

    @property
    def help_text(self) -> str:
        return _('Filter out players with a lower rating.')


class MaxRatingOption(RatingPlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'MAX_RATING'

    @property
    def label(self) -> str:
        return _('Maximum rating')

    @property
    def help_text(self) -> str:
        return _('Filter out players with a greater rating.')


class AgeCategoriesOption(PlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'AGE_CATEGORIES'

    @property
    def template_file_name(self) -> str:
        return 'age_categories'

    @property
    def type(self) -> type | UnionType:
        return list[int]

    @property
    def default_value(self) -> Any:
        return []

    @property
    def age_category_options(self) -> dict[str, str]:
        return {
            str(category.value): category.short_name
            for category in PlayerCategory
            if category != PlayerCategory.NONE
        }

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
        return _('Include players of lower categories')

    @property
    def other_field_id(self) -> str:
        return AgeGreaterOption.static_id()


class AgeGreaterOption(AgeRangePlayerFilterOption):
    @staticmethod
    def static_id() -> str:
        return 'AGE_GREATER'

    @property
    def field_placeholder(self) -> str:
        return _('Include players of greater categories')

    @property
    def other_field_id(self) -> str:
        return AgeLowerOption.static_id()
