from abc import ABC, abstractmethod
from typing import Any

from common.i18n import _
from data.player import TournamentPlayer
from data.print_documents.teams import ClubTeam, FederationTeam
from utils.entity import IdentifiableEntity


class TeamType(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def team_class(self) -> type:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_player_entity(player: TournamentPlayer) -> Any | None:
        """Returns the entity the player belongs to (club, federation...), or None."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def document_title(round_: int) -> str:
        """Returns the main title of the document."""
        raise NotImplementedError

    @property
    @abstractmethod
    def overall_table_header(self) -> str:
        """Returns the string used for the team column header."""
        raise NotImplementedError

    @property
    @abstractmethod
    def max_teams_per_entity_label(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def max_teams_per_entity_tooltip(self) -> str:
        raise NotImplementedError


class ClubTeamType(TeamType):
    @staticmethod
    def static_id() -> str:
        return 'club-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Players from the same club')

    @property
    def team_class(self) -> type:
        return ClubTeam

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> Any | None:
        return player.club if player.club.name else None

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by club after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('Club')

    @property
    def max_teams_per_entity_label(self) -> str:
        return _('Teams per club:')

    @property
    def max_teams_per_entity_tooltip(self) -> str:
        return _('The maximum number of teams per club.')


class FederationTeamType(TeamType):
    @staticmethod
    def static_id() -> str:
        return 'federation-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Players from the same federation')

    @property
    def team_class(self) -> type:
        return FederationTeam

    @staticmethod
    def get_player_entity(player: TournamentPlayer) -> Any | None:
        return player.federation if player.federation.name else None

    @staticmethod
    def document_title(round_: int) -> str:
        return _('Ranking by federation after round #{round}').format(round=round_)

    @property
    def overall_table_header(self) -> str:
        return _('Federation')

    @property
    def max_teams_per_entity_label(self) -> str:
        return _('Teams per federation:')

    @property
    def max_teams_per_entity_tooltip(self) -> str:
        return _('The maximum number of teams per federation.')
