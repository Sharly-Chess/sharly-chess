from abc import ABC, abstractmethod
from operator import attrgetter
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings.settings import BergerNumbersSetting
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from data.team import Team


class GridPlayerSorter(IdentifiableEntity, ABC):
    @abstractmethod
    def sorted_tournament_players(
        self, tournament: Tournament
    ) -> list[TournamentPlayer]:
        """Get a sorted list of all the players in a tournament."""


class NameGridPlayerSorter(GridPlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'grid-name'

    @staticmethod
    def static_name() -> str:
        return _('Name')

    def sorted_tournament_players(
        self, tournament: Tournament
    ) -> list[TournamentPlayer]:
        return tournament.sorted_tournament_players


class RankGridPlayerSorter(GridPlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'grid-rank'

    @staticmethod
    def static_name() -> str:
        return _('Rank')

    def sorted_tournament_players(
        self, tournament: Tournament
    ) -> list[TournamentPlayer]:
        return [
            tournament_player
            for tournament_player in tournament.compute_tournament_player_ranks(
                after_round=tournament.rounds
            ).values()
        ]


class StartingRankGridPlayerSorter(GridPlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'grid-starting-rank'

    @staticmethod
    def static_name() -> str:
        return _('Starting rank')

    def sorted_tournament_players(
        self, tournament: Tournament
    ) -> list[TournamentPlayer]:
        return [
            tournament_player
            for tournament_player in tournament.tournament_players_by_starting_rank.values()
        ]


class PairingNumberGridPlayerSorter(GridPlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'grid-pairing-number'

    @staticmethod
    def static_name() -> str:
        return _('Pairing number')

    def sorted_tournament_players(
        self, tournament: Tournament
    ) -> list[TournamentPlayer]:
        berger_nb_by_player_id = BergerNumbersSetting.get_value(tournament)
        return sorted(
            tournament.tournament_players,
            key=lambda p: berger_nb_by_player_id[p.id],
        )


class TeamGridSorter(IdentifiableEntity, ABC):
    @abstractmethod
    def sorted_teams(self, tournament: Tournament) -> list['Team']:
        """Get a sorted list of all the teams in a tournament."""


class RankTeamGridSorter(TeamGridSorter):
    @staticmethod
    def static_id() -> str:
        return 'team-grid-rank'

    @staticmethod
    def static_name() -> str:
        return _('Rank')

    def sorted_teams(self, tournament: Tournament) -> list['Team']:
        return [row['team'] for row in tournament.team_standings()]


class PairingNumberTeamGridSorter(TeamGridSorter):
    @staticmethod
    def static_id() -> str:
        return 'team-grid-pairing-number'

    @staticmethod
    def static_name() -> str:
        return _('Pairing number')

    def sorted_teams(self, tournament: Tournament) -> list['Team']:
        return sorted(
            tournament.teams,
            key=lambda team: (
                team.pairing_number
                if team.pairing_number is not None
                else float('inf'),
                team.name.lower(),
            ),
        )


class NameTeamGridSorter(TeamGridSorter):
    @staticmethod
    def static_id() -> str:
        return 'team-grid-name'

    @staticmethod
    def static_name() -> str:
        return _('Name')

    def sorted_teams(self, tournament: Tournament) -> list['Team']:
        return sorted(tournament.teams, key=lambda team: team.name.lower())


class ListPlayerSorter(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def sort_key(self) -> str:
        """Get the attr key used to sort the players."""

    def sort_tournament_players(
        self, tournament_players: list[TournamentPlayer]
    ) -> list[TournamentPlayer]:
        """Sort the given tournament players."""
        return sorted(
            tournament_players,
            key=attrgetter(self.sort_key),
        )


class NameListPlayerSorter(ListPlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'list-name'

    @staticmethod
    def static_name() -> str:
        return _('Name')

    @property
    def sort_key(self) -> str:
        return 'name_sort_key'


class StartingRankListPlayerSorter(ListPlayerSorter):
    @staticmethod
    def static_id() -> str:
        return 'list-starting-rank'

    @staticmethod
    def static_name() -> str:
        return _('Starting rank')

    @property
    def sort_key(self) -> str:
        return 'starting_rank_sort_key'
