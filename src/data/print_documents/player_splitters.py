from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Iterable

from common.i18n import _
from common.i18n.utils import normalized_key
from data.event import Event
from data.player import TournamentPlayer
from utils.entity import IdentifiableEntity


class PlayerSplitter(IdentifiableEntity, ABC):
    @staticmethod
    @abstractmethod
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        """Extract the split key from a player.
        Players will be grouped by split key."""

    @staticmethod
    def get_empty_key_default() -> str:
        """Return the string to use for eventual empty split key."""
        return ''

    @staticmethod
    def sorted_split_keys(event: Event, split_keys: Iterable[str]) -> list[str]:
        """Returns the split keys ordered. Defaults to alphabetical sort."""
        return sorted(split_keys, key=normalized_key)

    def split_players(
        self, event: Event, tournament_players: list[TournamentPlayer]
    ) -> dict[str, list[TournamentPlayer]]:
        split_players = defaultdict(list)
        for tournament_player in tournament_players:
            split_players[self.get_split_key(tournament_player)].append(
                tournament_player
            )
        return {
            key or self.get_empty_key_default(): split_players[key]
            for key in self.sorted_split_keys(event, split_players.keys())
        }


class NoSplitPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'no-split'

    @staticmethod
    def static_name() -> str:
        return '-'

    @staticmethod
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        return ''


class CategoryPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'category'

    @staticmethod
    def static_name() -> str:
        return _('Category')

    @staticmethod
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        return tournament_player.category.name

    @staticmethod
    def sorted_split_keys(event: Event, split_keys: Iterable[str]) -> list[str]:
        ordered_keys = [category.name for category in event.player_categories]
        return sorted(split_keys, key=lambda key: ordered_keys.index(key))


class ClubPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'club'

    @staticmethod
    def static_name() -> str:
        return _('Club')

    @staticmethod
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        return tournament_player.club.name if tournament_player.club else ''

    @staticmethod
    def get_empty_key_default() -> str:
        return _('No club')


class FederationPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'federation'

    @staticmethod
    def static_name() -> str:
        return _('Federation')

    @staticmethod
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        return tournament_player.federation.name
