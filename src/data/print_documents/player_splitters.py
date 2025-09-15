from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Iterable

from common.i18n import _
from data.player import Player
from utils.entity import IdentifiableEntity
from utils.enum import PlayerCategory


class PlayerSplitter(IdentifiableEntity, ABC):
    @staticmethod
    @abstractmethod
    def get_split_key(player: Player) -> str:
        """Extract the split key from a player.
        Players will be grouped by split key."""

    @staticmethod
    def sorted_split_keys(split_keys: Iterable[str]) -> list[str]:
        """Returns the split keys ordered. Defaults to alphabetical sort."""
        return sorted(split_keys)

    def split_players(self, players: list[Player]) -> dict[str, list[Player]]:
        split_players = defaultdict(list)
        for player in players:
            split_players[self.get_split_key(player)].append(player)
        return {
            key: split_players[key]
            for key in self.sorted_split_keys(split_players.keys())
        }


class NoSplitPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'no-split'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return '-'

    @staticmethod
    def get_split_key(player: Player) -> str:
        return ''


class CategoryPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'category'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Category', locale)

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.category.short_name

    @staticmethod
    def sorted_split_keys(split_keys: Iterable[str]) -> list[str]:
        ordered_keys = [category.short_name for category in PlayerCategory]
        return sorted(split_keys, key=lambda key: ordered_keys.index(key))


class ClubPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'club'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Club', locale)

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.club.name if player.club else ''


class FederationPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'federation'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Federation', locale)

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.federation.name
