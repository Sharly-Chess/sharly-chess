from abc import ABC, abstractmethod

from common.i18n import _
from data.pairings.settings import BergerNumbersSetting
from data.player import Player
from data.tournament import Tournament
from utils.entity import IdentifiableEntity


class PlayerSorter(IdentifiableEntity, ABC):
    @abstractmethod
    def sorted_players(self, tournament: Tournament) -> list[Player]:
        """Get a sorted list of all the players in a tournament."""


class NamePlayerSorter(PlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'name'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Name', locale)

    def sorted_players(self, tournament: Tournament) -> list[Player]:
        return tournament.players_by_name_with_unpaired


class RankPlayerSorter(PlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'rank'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Rank', locale)

    def sorted_players(self, tournament: Tournament) -> list[Player]:
        return [
            player
            for player in tournament.compute_player_ranks(
                after_round=tournament.rounds
            ).values()
        ]


class StartingRankPlayerSorter(PlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'starting-rank'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Starting rank', locale)

    def sorted_players(self, tournament: Tournament) -> list[Player]:
        return [player for player in tournament.players_by_starting_rank.values()]


class PairingNumberPlayerSorter(PlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'pairing-number'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Pairing number', locale)

    def sorted_players(self, tournament: Tournament) -> list[Player]:
        berger_nb_by_player_id = BergerNumbersSetting.get_value(tournament)
        return sorted(
            tournament.players,
            key=lambda p: berger_nb_by_player_id[p.id],
        )
