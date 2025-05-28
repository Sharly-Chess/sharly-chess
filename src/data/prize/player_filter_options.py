from abc import ABC
from types import UnionType
from typing import Any

from utils.enum import PlayerGender
from utils.option import Option, OptionError


class PlayerFilterOption(Option, ABC):
    """Parent class of all the option of player filters."""


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
    def template_name(self) -> str:
        return ''

    def validate(self):
        super().validate()
        try:
            PlayerGender(self.value)
        except ValueError:
            raise OptionError(f'Invalid gender value: {self.value}', self)
