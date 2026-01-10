from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, TYPE_CHECKING

from common.exception import OptionError
from common.i18n import _
from data.account import Account
from data.event import Event
from data.player import TournamentPlayer
from data.print_documents import PrintOption
from data.tournament import Tournament
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from utils.entity import IdentifiableEntity
from utils.enum import RoleType, PlayerRatingType
from utils.time_control import trf25_to_human_readable

if TYPE_CHECKING:
    from plugins.ffe.print_documents.ffe_documents import FFEPrintDocument


class FFEDocumentType(IdentifiableEntity, ABC):
    def __init__(self):
        self._ffe_document: FFEPrintDocument | None = None

    def set_ffe_document(
        self,
        ffe_document: 'FFEPrintDocument',
    ):
        self._ffe_document = ffe_document

    @property
    def ffe_document(self) -> 'FFEPrintDocument':
        assert self._ffe_document is not None, 'set_ffe_document() has not been called.'
        return self._ffe_document

    @property
    def title(self) -> str:
        return self.static_name()

    @classmethod
    def get_valid_option_ids(cls) -> list[str]:
        return [option.static_id() for option in cls.get_valid_option_types()]

    @staticmethod
    def get_valid_option_types() -> list[type[PrintOption]]:
        """Returns a list of valid options for the document type."""
        from plugins.ffe.print_documents.ffe_options import FFEDocumentTypePrintOption

        return [FFEDocumentTypePrintOption]

    def validate_options(
        self,
        ffe_document: 'FFEPrintDocument',
    ):
        self.set_ffe_document(ffe_document)

    @classmethod
    def get_template_name(cls) -> str:
        """Returns the body template."""
        return f'/print/{cls.static_id().replace("-", "_")}.html'

    @cached_property
    def event(self) -> Event:
        return self.ffe_document.event

    @property
    def date(self) -> str:
        """Returns the date of the doc, as a printable string."""
        return datetime.now().strftime('%d/%m/%Y')

    @cached_property
    @abstractmethod
    def _accounts_by_role(self) -> dict[RoleType, set[Account]]:
        """Returns a dict made of the accounts by role."""

    @cached_property
    def chief_arbiters(self) -> list[Account]:
        """Returns the lists of chief arbiters."""
        return sorted(
            self._accounts_by_role[RoleType.CHIEF_ARBITER], key=lambda a: a.full_name
        )

    @cached_property
    def deputy_arbiters(self) -> list[Account]:
        """Returns the lists of deputy arbiters."""
        return sorted(
            (
                account
                for account in self._accounts_by_role[RoleType.DEPUTY_ARBITER]
                if account not in self.chief_arbiters
            ),
            key=lambda a: a.full_name,
        )

    @cached_property
    def organisers(self) -> list[Account]:
        """Returns the lists of organisers."""
        return sorted(
            self._accounts_by_role[RoleType.ORGANISER], key=lambda a: a.full_name
        )

    @cached_property
    def writer(self) -> Account | None:
        """Returns the account of the document writer, if any."""
        account: Account = self.ffe_document.client.account
        if not account.administrator and not account.anonymous:
            return account
        if self.chief_arbiters:
            return self.chief_arbiters[0]
        if self.deputy_arbiters:
            return self.deputy_arbiters[0]
        return None

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        self.set_ffe_document(ffe_document)
        return {
            'event': self.event,
            'date': self.date,
            'writer': self.writer,
            'arbiters': self.chief_arbiters + self.deputy_arbiters,
            'organisers': self.organisers,
        }


class FFETournamentsDocumentType(FFEDocumentType, ABC):
    @staticmethod
    def get_valid_option_types() -> list[type['PrintOption']]:
        from data.print_documents.options import TournamentsPrintOption

        return FFEDocumentType.get_valid_option_types() + [
            TournamentsPrintOption,
        ]

    @cached_property
    def tournaments(self) -> list[Tournament]:
        return self.ffe_document.tournaments

    @cached_property
    def _accounts_by_role(self) -> dict[RoleType, set[Account]]:
        """Returns a dict made of the accounts by role."""
        accounts_by_role: dict[RoleType, set[Account]] = {
            role_type: set()
            for role_type in [
                RoleType.CHIEF_ARBITER,
                RoleType.DEPUTY_ARBITER,
                RoleType.ORGANISER,
            ]
        }
        for account_id, account in self.event.accounts_by_id.items():
            if not account.administrator and not account.anonymous:
                if account.roles:
                    for role in account.roles:
                        if role.tournament_ids is not None:
                            for tournament_id in role.tournament_ids:
                                if tournament_id in (
                                    tournament.id for tournament in self.tournaments
                                ):
                                    accounts_by_role[role.role_type].add(account)
        return accounts_by_role

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'tournaments': self.tournaments,
        }


class FFET1T2Type(FFETournamentsDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t1-t2-tournament-report'

    @staticmethod
    def static_name() -> str:
        return 'T1-T2 Rapport technique'

    @property
    def tournaments_name(self) -> str:
        """Returns the name for the tournaments."""
        tournaments_name: str = self.event.name
        if self.tournaments and len(self.tournaments) != len(self.event.tournaments):
            tournaments_name += (
                f' ({", ".join(tournament.name for tournament in self.tournaments)})'
            )
        return tournaments_name

    @property
    def tournaments_date(self) -> str:
        """Returns the date for the tournaments, as a printable string."""
        if self.tournaments and len(self.tournaments) != len(self.event.tournaments):
            start_date_min = min(
                tournament.start_date for tournament in self.tournaments
            )
            stop_date_max = max(
                tournament.start_date for tournament in self.tournaments
            )
        else:
            start_date_min = self.event.start_date
            stop_date_max = self.event.stop_date
        tournaments_date: str = start_date_min.strftime('%d/%m/%Y')
        if start_date_min != stop_date_max:
            tournaments_date += f' - {stop_date_max.strftime("%d/%m/%Y")}'
        return tournaments_date

    @property
    def tournaments_prizes_sharing_systems(self) -> str:
        """Returns the prizes sharing systems of the document, as a printable string."""
        sharing_systems: set[str] = set()
        for tournament in self.tournaments:
            for prize_group in tournament.prize_groups:
                for category in prize_group.categories:
                    if category.is_main:
                        sharing_systems.add(category.prize_sharing.name)
        return ', '.join(sharing_systems)

    @property
    def tournaments_prizes_total(self) -> float:
        """Returns the prizes total of the document."""
        prizes_total: float = 0.0
        for tournament in self.tournaments:
            for prize_group in tournament.prize_groups:
                for category in prize_group.categories:
                    for prize in category.prizes:
                        if prize.is_monetary:
                            prizes_total += prize.value
        return prizes_total

    @property
    def tournament_ffe_ids(self) -> str:
        """Returns the list of the tournaments' FFE ID, as a printable string."""
        return ', '.join(
            str(FFEUtils.get_tournament_plugin_data(tournament).ffe_id)
            for tournament in self.tournaments
            if FFEUtils.get_tournament_plugin_data(tournament).ffe_id
        )

    @property
    def tournaments_rounds(self) -> str:
        """Returns the list of the tournaments' rounds, as a printable string."""
        return '/'.join(
            sorted(set(str(tournament.rounds) for tournament in self.tournaments))
        )

    @property
    def tournaments_time_control(self) -> str:
        """Returns the list of the tournaments' time control, as a printable string."""
        return ', '.join(
            sorted(
                set(
                    trf25_to_human_readable(tournament.time_control_trf25)
                    for tournament in self.tournaments
                )
            )
        )

    @property
    def tournaments_pairing(self) -> str:
        """Returns the list of the tournaments' pairing, as a printable string."""
        return ', '.join(
            sorted(
                set(
                    f'{tournament.pairing_system.name} - {tournament.pairing_variation.name}'
                    for tournament in self.tournaments
                )
            )
        )

    @property
    def tournaments_tie_breaks(self) -> str:
        """Returns the list of the tournaments' tiebreaks, as a printable string."""
        return ' '.join(
            sorted(
                set(
                    ', '.join(tie_break.acronym for tie_break in tournament.tie_breaks)
                    for tournament in self.tournaments
                )
            )
        )

    @property
    def tournaments_location(self) -> str:
        """Returns the list of the tournaments' location, as a printable string."""
        return ' '.join(
            sorted(
                set(
                    tournament.location
                    for tournament in self.tournaments
                    if tournament.location
                )
            )
        )

    @property
    def _tournaments_players_counts(self) -> tuple[int, int]:
        """Returns the counts of FIDE and total players count as a 2-tuple."""
        return sum(
            len(
                [
                    player
                    for player in tournament.tournament_players_by_id.values()
                    if player.rating_type == PlayerRatingType.FIDE
                ]
            )
            for tournament in self.tournaments
        ), sum(tournament.player_count for tournament in self.tournaments)

    @property
    def tournaments_fide_players_count(self) -> int:
        """Returns the counts of FIDE players."""
        fide_players_count, _ = self._tournaments_players_counts
        return fide_players_count

    @property
    def tournaments_total_players_count(self) -> int:
        """Returns the counts of players."""
        _, total_players_count = self._tournaments_players_counts
        return total_players_count

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'event_date': self.tournaments_date,
            'event_name': self.tournaments_name,
            'ffe_ids': self.tournament_ffe_ids,
            'rounds': self.tournaments_rounds,
            'time_control': self.tournaments_time_control,
            'pairing': self.tournaments_pairing,
            'tie_breaks': self.tournaments_tie_breaks,
            'location': self.tournaments_location,
            'fide_player_count': self.tournaments_fide_players_count,
            'total_player_count': self.tournaments_total_players_count,
            'prizes_total': f'{self.tournaments_prizes_total:.2f}',
            'prizes_sharing': self.tournaments_prizes_sharing_systems,
        }


class FFETournamentDocumentType(FFEDocumentType, ABC):
    @staticmethod
    def get_valid_option_types() -> list[type['PrintOption']]:
        from data.print_documents.options import TournamentPrintOption

        return FFEDocumentType.get_valid_option_types() + [
            TournamentPrintOption,
        ]

    @cached_property
    def tournament(self) -> Tournament:
        return self.ffe_document.tournament

    @property
    def tournament_name(self) -> str:
        """Returns the name for the tournament."""
        tournament_name: str = self.event.name
        if len(self.event.tournaments) > 1:
            tournament_name += f' ({self.tournament.name})'
        return tournament_name

    @property
    def tournament_date(self) -> str:
        """Returns the date of the tournament, as a printable string."""
        tournaments_date: str = self.tournament.start_date.strftime('%d/%m/%Y')
        if self.tournament.start_date != self.tournament.stop_date:
            tournaments_date += f' - {self.tournament.stop_date.strftime("%d/%m/%Y")}'
        return tournaments_date

    @cached_property
    def _accounts_by_role(self) -> dict[RoleType, set[Account]]:
        """Returns a dict made of the accounts by role."""
        accounts_by_role: dict[RoleType, set[Account]] = {
            role_type: set()
            for role_type in [
                RoleType.CHIEF_ARBITER,
                RoleType.DEPUTY_ARBITER,
                RoleType.ORGANISER,
            ]
        }
        for account_id, account in self.event.accounts_by_id.items():
            if not account.administrator and not account.anonymous:
                if account.roles:
                    for role in account.roles:
                        if role.tournament_ids is not None:
                            if self.tournament.id in role.tournament_ids:
                                accounts_by_role[role.role_type].add(account)
        return accounts_by_role

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'tournament': self.tournament,
            'tournament_name': self.tournament_name,
            'tournament_date': self.tournament_date,
            'location': self.tournament.location,
        }


class FFEPlayersDocumentType(FFETournamentDocumentType, ABC):
    @staticmethod
    def get_valid_option_types() -> list[type['PrintOption']]:
        from data.print_documents.options import PlayersPrintOption

        return FFETournamentDocumentType.get_valid_option_types() + [
            PlayersPrintOption,
        ]

    @cached_property
    def players(self) -> list[TournamentPlayer]:
        return self.ffe_document.players

    def validate_options(
        self,
        ffe_document: 'FFEPrintDocument',
    ):
        from data.print_documents.options import PlayersPrintOption

        super().validate_options(ffe_document)
        if not self.players:
            raise OptionError(
                _('Please select at least one player.'),
                self.ffe_document._get_option(PlayersPrintOption),
            )

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'players': self.players,
        }


class FFET3T4Type(FFEPlayersDocumentType):
    @staticmethod
    def get_valid_option_types() -> list[type['PrintOption']]:
        from plugins.ffe.print_documents.ffe_options import FFELicencePrintOption

        return FFEPlayersDocumentType.get_valid_option_types() + [
            FFELicencePrintOption,
        ]

    @staticmethod
    def static_id() -> str:
        return 'ffe-t3-t4-players-licence'

    @staticmethod
    def static_name() -> str:
        return 'T3-T4 Attestation de licence'

    @cached_property
    def ffe_licence(self) -> PlayerFFELicence:
        return self.ffe_document.ffe_licence

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'ffe_licence': self.ffe_licence,
        }


class FFEPlayerDocumentType(FFETournamentDocumentType, ABC):
    @staticmethod
    def get_valid_option_types() -> list[type['PrintOption']]:
        from data.print_documents.options import PlayerPrintOption

        return FFETournamentDocumentType.get_valid_option_types() + [
            PlayerPrintOption,
        ]

    @cached_property
    def player(self) -> TournamentPlayer:
        return self.ffe_document.player

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'player': self.player,
        }


class FFET5Type(FFEPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t5-player-forfeit'

    @staticmethod
    def static_name() -> str:
        return 'T5 Enquête forfait non justifié'

    @property
    def response_date(self) -> str:
        return (datetime.now() + timedelta(days=2)).strftime('%d/%m/%Y')

    @property
    def player_first_forfeit_round(self) -> str:
        for round_ in range(1, self.player.tournament.rounds + 1):
            if self.player.pairings[round_].forfeit_loss:
                return str(round_)
        return ''

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'response_date': self.response_date,
            'player_first_forfeit_round': self.player_first_forfeit_round,
        }


class FFET6Type(FFEPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t6-player-exclusion'

    @staticmethod
    def static_name() -> str:
        return "T6 Exclusion d'un·e joueur·euse"


class FFET7Type(FFEPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t7-player-reporting'

    @staticmethod
    def static_name() -> str:
        return "T7 Signalement d'un·e joueur·euse"
