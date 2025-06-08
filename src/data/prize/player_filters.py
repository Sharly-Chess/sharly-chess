from abc import ABC, abstractmethod
from functools import cached_property

from common.i18n import _
from data.player import Player
from data.prize.player_filter_options import (
    PlayerFilterOption,
    GenderPlayerFilterOption,
)
from utils.enum import PlayerGender
from utils.option import OptionHandler


class PlayerFilter(OptionHandler[PlayerFilterOption], ABC):
    """Abstract class representing ways to filter the players."""

    @abstractmethod
    def is_player_included(self, player: Player) -> bool:
        """Check if a player is included in the filter or not."""

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
        return [GenderPlayerFilterOption]

    @cached_property
    def expected_gender(self) -> PlayerGender:
        return PlayerGender(self.get_option_values()[0])

    def is_player_included(self, player: Player) -> bool:
        return player.gender == self.expected_gender

    def __str__(self) -> str:
        return _('Gender ({gender})').format(gender=self.expected_gender.short_name)
