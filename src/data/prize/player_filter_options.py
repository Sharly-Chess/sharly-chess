from abc import ABC, abstractmethod
from types import UnionType
from typing import Any

from utils.enum import PlayerGender
from utils.option import Option, OptionError
from web.controllers.base_controller import WebContext


class PlayerFilterOption(Option, ABC):
    """Parent class of all the option of player filters."""

    @property
    def template_name(self) -> str:
        return self.template_dir + self.template_file

    @property
    def template_dir(self) -> str:
        return 'player_filter_options/'

    @property
    @abstractmethod
    def template_file(self) -> str:
        """Name of the file of the template representing the option."""


class GenderPlayerFilterOption(PlayerFilterOption):
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
    def template_file(self) -> str:
        return 'gender.html'

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
