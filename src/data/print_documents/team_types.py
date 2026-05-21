from abc import ABC, abstractmethod
from typing import Any

from common.i18n import _
from data.player import TournamentPlayer
from data.print_documents.teams import ClubIndividualTeam, FederationIndividualTeam
from utils.entity import IdentifiableEntity


class IndividualTeamType(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def team_class(self) -> type:
        """Returns the corresponding team class."""

    @staticmethod
    @abstractmethod
    def get_player_entity(player: TournamentPlayer) -> Any | None:
        """Returns the entity the player belongs to (club, federation...), or None."""

    @staticmethod
    @abstractmethod
    def document_title(round_: int) -> str:
        """Returns the main title of the document."""

    @property
    @abstractmethod
    def overall_table_header(self) -> str:
        """Returns the string used for the team column header."""

    @property
    def modal_info(self) -> dict[str, str | bool]:
        """Returns the information to display on the print modal as a dict."""
        return {
            'display_incomplete_tooltip': self.modal_info_display_incomplete_tooltip,
            'max_per_entity_label': self.modal_info_max_per_entity_label,
            'max_per_entity_tooltip': self.modal_info_max_per_entity_tooltip,
        }

    @property
    @abstractmethod
    def modal_info_max_per_entity_label(self) -> str:
        """Returns the label to use on the document modal for the "Max teams:" input."""

    @property
    @abstractmethod
    def modal_info_max_per_entity_tooltip(self) -> str:
        """Returns the tooltip to use on the document modal for the "Max teams:" input."""

    @property
    def modal_info_display_incomplete_tooltip(self) -> str:
        """Returns the tooltip to use on the document modal for the "Rank incomplete teams:" tooltip."""
        return _('Incomplete teams do have enough players or enough women/men.')


class ClubIndividualTeamType(IndividualTeamType):
    @staticmethod
    def static_id() -> str:
        return 'club-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Clubs')

    @property
    def team_class(self) -> type:
        return ClubIndividualTeam

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
    def modal_info_max_per_entity_label(self) -> str:
        return _('Number of teams per club:')

    @property
    def modal_info_max_per_entity_tooltip(self) -> str:
        return _('The maximum number of teams per club.')


class FederationIndividualTeamType(IndividualTeamType):
    @staticmethod
    def static_id() -> str:
        return 'federation-team-type'

    @staticmethod
    def static_name() -> str:
        return _('Federations')

    @property
    def team_class(self) -> type:
        return FederationIndividualTeam

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
    def modal_info_max_per_entity_label(self) -> str:
        return _('Teams per federation:')

    @property
    def modal_info_max_per_entity_tooltip(self) -> str:
        return _('The maximum number of teams per federation.')
