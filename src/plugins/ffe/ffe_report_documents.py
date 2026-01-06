from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, override, Iterator

from common.exception import OptionError
from common.i18n import _
from data.account import Account
from data.player import TournamentPlayer
from data.print_documents import PrintOption
from data.print_documents.documents import (
    PrintDocument,
)
from data.print_documents.options import (
    TournamentsPrintOption,
    PlayersPrintOption,
    TournamentPrintOption,
    PlayerPrintOption,
)
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from utils.enum import RoleType, PlayerRatingType
from utils.time_control import trf25_to_human_readable


class FFEEventReportPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'ffe-tournament-report'

    @staticmethod
    def static_name() -> str:
        return 'FFE Rapport technique T1/T2'

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [
            TournamentsPrintOption,
        ]

    @property
    def title(self) -> str:
        return self.static_name()

    @property
    def template_name(self) -> str:
        return 'print/ffe_tournament_report.html'

    @property
    def template_context(self) -> dict[str, Any]:
        accounts_by_role: dict[RoleType, set[Account]] = {
            role_type: set()
            for role_type in [
                RoleType.CHIEF_ARBITER,
                RoleType.DEPUTY_ARBITER,
                RoleType.ORGANISER,
            ]
        }
        assert self.event is not None
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
        chief_arbiters: list[Account] = sorted(
            accounts_by_role[RoleType.CHIEF_ARBITER], key=lambda a: a.full_name
        )
        deputy_arbiters: list[Account] = sorted(
            (
                account
                for account in accounts_by_role[RoleType.DEPUTY_ARBITER]
                if account not in chief_arbiters
            ),
            key=lambda a: a.full_name,
        )
        organisers: list[Account] = sorted(
            accounts_by_role[RoleType.ORGANISER], key=lambda a: a.full_name
        )
        writer: Account | None = None
        if chief_arbiters:
            writer = chief_arbiters[0]
        elif deputy_arbiters:
            writer = deputy_arbiters[0]
        event_date: str = self.event.start_date.strftime('%d/%m/%Y')
        if self.event.start_date != self.event.stop_date:
            event_date += f' - {self.event.stop_date.strftime("%d/%m/%Y")}'
        event_name: str = self.event.name
        if len(self.tournaments) != len(self.event.tournaments):
            event_name += (
                f' ({", ".join(tournament.name for tournament in self.tournaments)})'
            )
        prizes_total: float = 0.0
        for tournament in self.tournaments:
            for prize_group in tournament.prize_groups:
                for category in prize_group.categories:
                    for prize in category.prizes:
                        if prize.is_monetary:
                            prizes_total += prize.value
        sharing_systems: set[str] = set()
        for tournament in self.tournaments:
            for prize_group in tournament.prize_groups:
                for category in prize_group.categories:
                    if category.is_main:
                        sharing_systems.add(category.prize_sharing.name)
        prizes_sharing: str = ', '.join(sharing_systems)
        return {
            'event': self.event,
            'writer': writer,
            'event_date': event_date,
            'event_name': event_name,
            'arbiters': chief_arbiters + deputy_arbiters,
            'organisers': organisers,
            'tournament_ffe_ids': ', '.join(
                str(FFEUtils.get_tournament_plugin_data(tournament).ffe_id)
                for tournament in self.tournaments
                if FFEUtils.get_tournament_plugin_data(tournament).ffe_id
            ),
            'rounds': '/'.join(
                sorted(set(str(tournament.rounds) for tournament in self.tournaments))
            ),
            'time_control': ', '.join(
                sorted(
                    set(
                        trf25_to_human_readable(tournament.time_control_trf25)
                        for tournament in self.tournaments
                    )
                )
            ),
            'pairing': ', '.join(
                sorted(
                    set(
                        f'{tournament.pairing_system.name} - {tournament.pairing_variation.name}'
                        for tournament in self.tournaments
                    )
                )
            ),
            'tie_breaks': ' '.join(
                sorted(
                    set(
                        ', '.join(
                            tie_break.acronym for tie_break in tournament.tie_breaks
                        )
                        for tournament in self.tournaments
                    )
                )
            ),
            'fide_player_count': sum(
                len(
                    [
                        player
                        for player in tournament.tournament_players_by_id.values()
                        if player.rating_type == PlayerRatingType.FIDE
                    ]
                )
                for tournament in self.tournaments
            ),
            'player_count': sum(
                tournament.player_count for tournament in self.tournaments
            ),
            'prizes_total': f'{prizes_total:.2f}',
            'prizes_sharing': prizes_sharing,
            'date': datetime.now().strftime('%d/%m/%Y'),
        }


class FFETournamentPrintDocument(PrintDocument, ABC):
    @property
    def writer(self) -> Account | None:
        accounts_by_role: dict[RoleType, set[Account]] = {
            role_type: set()
            for role_type in [
                RoleType.CHIEF_ARBITER,
                RoleType.DEPUTY_ARBITER,
            ]
        }
        assert self.event is not None
        for account_id, account in self.event.accounts_by_id.items():
            if not account.administrator and not account.anonymous:
                if account.roles:
                    for role in account.roles:
                        if (
                            role.role_type
                            in [
                                RoleType.CHIEF_ARBITER,
                                RoleType.DEPUTY_ARBITER,
                            ]
                            and role.tournament_ids is not None
                        ):
                            for tournament_id in role.tournament_ids:
                                if tournament_id in (
                                    tournament.id for tournament in self.tournaments
                                ):
                                    accounts_by_role[role.role_type].add(account)
        chief_arbiters: list[Account] = sorted(
            accounts_by_role[RoleType.CHIEF_ARBITER], key=lambda a: a.full_name
        )
        if chief_arbiters:
            return chief_arbiters[0]
        deputy_arbiters: list[Account] = sorted(
            (
                account
                for account in accounts_by_role[RoleType.DEPUTY_ARBITER]
                if account not in chief_arbiters
            ),
            key=lambda a: a.full_name,
        )
        if deputy_arbiters:
            return deputy_arbiters[0]
        return None

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'writer': self.writer,
        }


class FFEPlayersLicencePrintDocument(FFETournamentPrintDocument, ABC):
    @staticmethod
    @abstractmethod
    def licence() -> PlayerFFELicence:
        """Returns the licence type expected by the form."""

    @staticmethod
    @abstractmethod
    def form_number() -> int:
        """Returns the number of the associated FFE form."""

    @classmethod
    def static_id(cls) -> str:
        return f'ffe-players-licence-{cls.licence().short_name.lower()}'

    @classmethod
    def static_name(cls) -> str:
        return f'FFE Attestation licence {cls.licence().short_name}'

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [
            TournamentPrintOption,
            PlayersPrintOption,
        ]

    @property
    def title(self) -> str:
        return self.static_name()

    @property
    def template_name(self) -> str:
        return 'print/ffe_players_licence.html'

    @property
    def _player_ids(self) -> Iterator[int]:
        return self._get_option(PlayersPrintOption).value

    @property
    def players(self) -> Iterator[TournamentPlayer]:
        return (
            self.tournament.tournament_players_by_id[player_id]
            for player_id in self._player_ids
        )

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.event is not None
        return super().template_context | {
            'players': self.players,
            'date': self.event.start_date.strftime('%d/%m/%Y'),
            'location': self.event.location,
        }

    @override
    def validate_options(self):
        super().validate_options()
        if not self._player_ids:
            raise OptionError(
                _('Please select at least one player.'),
                self._get_option(PlayersPrintOption),
            )


class FFEPlayersLicenceAPrintDocument(FFEPlayersLicencePrintDocument):
    @staticmethod
    def licence() -> PlayerFFELicence:
        return PlayerFFELicence.A

    @staticmethod
    def form_number() -> int:
        return 3


class FFEPlayersLicenceBPrintDocument(FFEPlayersLicencePrintDocument):
    @staticmethod
    def licence() -> PlayerFFELicence:
        return PlayerFFELicence.B

    @staticmethod
    def form_number() -> int:
        return 4


class FFEPlayerPrintDocument(FFETournamentPrintDocument, ABC):
    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [
            TournamentPrintOption,
            PlayerPrintOption,
        ]

    @property
    def title(self) -> str:
        return self.static_name()

    @property
    def player(self) -> TournamentPlayer:
        return self.tournament.tournament_players_by_id[
            self._get_option(PlayerPrintOption).value
        ]

    @property
    def event_date(self) -> str:
        assert self.event is not None
        event_date: str = self.event.start_date.strftime('%d/%m/%Y')
        if self.event.start_date != self.event.stop_date:
            event_date += f' - {self.event.stop_date.strftime("%d/%m/%Y")}'
        return event_date

    @property
    def event_name(self) -> str:
        assert self.event is not None
        return f'{self.event.name} - {self.player.tournament.name}'

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.event is not None
        return super().template_context | {
            'player': self.player,
            'date': datetime.now().strftime('%d/%m/%Y'),
            'location': self.event.location,
        }


class FFEPlayerForfeitPrintDocument(FFEPlayerPrintDocument):
    @classmethod
    def static_id(cls) -> str:
        return 'ffe-player-forfeit'

    @classmethod
    def static_name(cls) -> str:
        return 'FFE Enquête forfait non justifié'

    @property
    def template_name(self) -> str:
        return 'print/ffe_player_forfeit.html'

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.event is not None
        return super().template_context | {
            'response_date': (self.event.stop_date + timedelta(days=2)).strftime(
                '%d/%m/%Y'
            ),
        }


class FFEPlayerExclusionPrintDocument(FFEPlayerPrintDocument):
    @classmethod
    def static_id(cls) -> str:
        return 'ffe-player-exclusion'

    @classmethod
    def static_name(cls) -> str:
        return 'FFE Exclusion joueur·euse'

    @property
    def template_name(self) -> str:
        return 'print/ffe_player_exclusion.html'


class FFEPlayerReportingPrintDocument(FFEPlayerPrintDocument):
    @classmethod
    def static_id(cls) -> str:
        return 'ffe-player-reporting'

    @classmethod
    def static_name(cls) -> str:
        return 'FFE Signalement joueur·euse'

    @property
    def template_name(self) -> str:
        return 'print/ffe_player_reporting.html'
