import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from functools import cached_property
from typing import Any, TYPE_CHECKING

from common import BASE_DIR
from common.i18n import _
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.client import Client
from data.account import Account
from data.event import Event
from data.player import TournamentPlayer
from data.print_documents import PrintOption
from data.tournament import Tournament
from plugins.ffe import PLUGIN_DIR
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from utils.entity import IdentifiableEntity
from utils.enum import RoleType, PlayerRatingType
from utils.file import image_file_inline_url, ttf_file_inline_url
from utils.time_control import trf25_to_human_readable

if TYPE_CHECKING:
    from plugins.ffe.print_documents.ffe_documents import FFEPrintDocument
    from plugins.ffe.print_documents.ffe_options import FFENoLicencePlayersPrintOption

logger: logging.Logger = get_logger()


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

    @classmethod
    @abstractmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        """Returns a list of valid options for the document type."""

    def validate_options(
        self,
        ffe_document: 'FFEPrintDocument',
    ):
        self.set_ffe_document(ffe_document)

    @classmethod
    def get_template_name(cls) -> str:
        """Returns the body template."""
        return f'/print/{cls.get_template_stem()}.html'

    @classmethod
    def get_template_stem(cls) -> str:
        """Returns the stem of the body template."""
        return cls.static_id().replace('-', '_')

    @cached_property
    def event(self) -> Event:
        return self.ffe_document.get_event()

    @cached_property
    def client(self) -> Client:
        return self.ffe_document.get_client()

    @property
    def date(self) -> str:
        """Returns the date of the doc, as a printable string."""
        return datetime.now().strftime('%d/%m/%Y')

    @property
    def event_name(self) -> str:
        """Returns the name of the event, as a printable string."""
        return self.event.name

    @property
    def event_date(self) -> str:
        """Returns the date for the event, as a printable string."""
        event_date: str = self.event.start_date.strftime('%d/%m/%Y')
        if self.event.start_date != self.event.stop_date:
            event_date += f' - {self.event.stop_date.strftime("%d/%m/%Y")}'
        return event_date

    @property
    def event_days(self) -> int:
        """Returns the number of days for the tournaments."""
        return (self.event.stop_date - self.event.start_date).days + 1

    @cached_property
    def tournaments(self) -> list[Tournament]:
        return self.ffe_document.get_allowed_tournaments()

    @cached_property
    def arbiters(self) -> str:
        """Returns the lists of arbiters, chief arbiters first then deputy arbiters, as a textarea string."""
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

        def format_arbiter(arbiter: Account) -> str:
            return ' '.join(
                item
                for item in [
                    arbiter.last_name,
                    arbiter.first_name,
                    FFEUtils.get_account_plugin_data(arbiter).ffe_licence_number,
                    FFEUtils.get_account_plugin_data(
                        arbiter
                    ).ffe_arbiter_title.short_name,
                ]
                if item
            )

        return (
            f'Arbitres en chef :\n{", ".join(format_arbiter(arbiter) for arbiter in chief_arbiters)}\n\n'
            f'Arbitres adjoint·es :\n{", ".join(format_arbiter(arbiter) for arbiter in deputy_arbiters)}\n'
        )

    @cached_property
    def writer(self) -> Account | None:
        from plugins.ffe.print_documents.ffe_options import FFEWriterPrintOption

        if account_id := self.ffe_document._get_option(FFEWriterPrintOption).value:
            return self.event.accounts_by_id[account_id]
        else:
            return None

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

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        self.set_ffe_document(ffe_document)
        font_file = (
            BASE_DIR / 'src/web/static/fonts/AtkinsonHyperlegibleNextVF-Variable.ttf'
        )
        return {
            'sharly_chess_config': SharlyChessConfig(),
            'font_family': font_file.stem,
            'font_url': ttf_file_inline_url(font_file),
            'ffe_logo_url': image_file_inline_url(
                PLUGIN_DIR / 'static/images/ffe-text.png'
            ),
            'event': self.event,
            'event_name': self.event_name,
            'event_date': self.event_date,
            'event_days': self.event_days,
            'date': self.date,
            'writer': self.writer,
            'rounds': self.tournaments_rounds,
            'time_control': self.tournaments_time_control,
            'ffe_ids': self.tournament_ffe_ids,
            'arbiters': self.arbiters,
        }


class FFETrainingCertificateType(FFEDocumentType, ABC):
    @classmethod
    def get_template_stem(cls) -> str:
        return 'ffe_training_certificate'

    @classmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        from plugins.ffe.print_documents.ffe_options import (
            FFEDocumentTypePrintOption,
            FFEWriterPrintOption,
            FFETraineePrintOption,
        )

        return [
            FFEDocumentTypePrintOption,
            FFEWriterPrintOption,
            FFETraineePrintOption,
        ]

    @property
    @abstractmethod
    def training_skills(self) -> list[str]:
        """Returns the skills expected for the training."""

    @property
    @abstractmethod
    def training_levels(self) -> list[str]:
        """Returns the evaluation levels for the training."""

    @property
    @abstractmethod
    def training_title(self) -> str:
        """Returns the arbiter title for the training."""

    @cached_property
    def trainee(self) -> Account | None:
        from plugins.ffe.print_documents.ffe_options import FFETraineePrintOption

        if account_id := self.ffe_document._get_option(FFETraineePrintOption).value:
            return self.event.accounts_by_id[account_id]
        else:
            return None

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        self.set_ffe_document(ffe_document)
        return super().template_context(ffe_document) | {
            'training_skills': self.training_skills,
            'training_levels': self.training_levels,
            'training_title': self.training_title,
            'trainee': self.trainee,
        }


class FFETrainingCertificate1Type(FFETrainingCertificateType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-training-certificate-1'

    @staticmethod
    def static_name() -> str:
        return 'Attestation de stage pratique AFC'

    @property
    def training_title(self) -> str:
        return 'AFC'

    @property
    def training_skills(self) -> list[str]:
        return [
            'Connaitre les règles du jeu',
            'Maitrise du règlement de la compétition',
            'Représenter dignement l’équipe d’arbitrage',
            'Régler une pendule',
            'Vérifier la mise en place en début de ronde',
            'Présence',
            'Intervenir sur une partie',
            'Se questionner/se concerter avec les autres arbitres',
            'Connaissance générale de la Fédération et de la D.N.A.',
            'Compétences organisationnelles',
        ]

    @property
    def training_levels(self) -> list[str]:
        return [
            'Parfait',
            'Satisfaisant',
            'Fragile',
            'Insuffisant',
        ]


class FFETrainingCertificate2Type(FFETrainingCertificateType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-training-certificate-2'

    @staticmethod
    def static_name() -> str:
        return 'Attestation de stage pratique AFO'

    @property
    def training_title(self) -> str:
        return 'AFO'

    @property
    def training_skills(self) -> list[str]:
        return [
            'Maitrise du logiciel Papi',
            'Connaissance et maitrise de sa mission administrative',
            'Maitrise du règlement de la compétition',
            'Représenter dignement l’équipe d’arbitrage',
            'Non évalué Relations avec l’organisateur',
            'Calcul des prix',
            'Système suisse et départages',
            'Se questionner/se concerter avec les autres arbitres',
        ]

    @property
    def training_levels(self) -> list[str]:
        return ['Parfait', 'Satisfaisant', 'Fragile', 'Insuffisant', 'Non évalué']


class FFETournamentsDocumentType(FFEDocumentType, ABC):
    @classmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        from data.print_documents.options import TournamentsPrintOption
        from plugins.ffe.print_documents.ffe_options import FFEDocumentTypePrintOption

        return [
            FFEDocumentTypePrintOption,
            TournamentsPrintOption,
        ]

    @cached_property
    def tournaments(self) -> list[Tournament]:
        return self.ffe_document.tournaments

    @property
    def tournaments_name(self) -> str:
        """Returns the name for the tournaments."""
        tournaments_name: str = self.event_name
        if self.tournaments and len(self.tournaments) != len(self.event.tournaments):
            tournaments_name += (
                f' ({", ".join(tournament.name for tournament in self.tournaments)})'
            )
        return tournaments_name

    @cached_property
    def _tournaments_dates(self) -> tuple[date, date]:
        """Returns the start and stop dates for the tournaments."""
        if self.tournaments and len(self.tournaments) != len(self.event.tournaments):
            return (
                min(tournament.start_date for tournament in self.tournaments),
                max(tournament.stop_date for tournament in self.tournaments),
            )
        else:
            return (
                self.event.start_date,
                self.event.stop_date,
            )

    @property
    def tournaments_date(self) -> str:
        """Returns the date for the tournaments, as a printable string."""
        start_date, stop_date = self._tournaments_dates
        tournaments_date: str = start_date.strftime('%d/%m/%Y')
        if start_date != stop_date:
            tournaments_date += f' - {stop_date.strftime("%d/%m/%Y")}'
        return tournaments_date

    @property
    def tournaments_days(self) -> int:
        """Returns the number of days for the tournaments."""
        start_date, stop_date = self._tournaments_dates
        return (stop_date - start_date).days + 1

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

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'event_name': self.tournaments_name,
            'event_date': self.tournaments_date,
            'event_days': self.tournaments_days,
            'location': self.tournaments_location,
        }


class FFET1Type(FFETournamentsDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t1-cover'

    @staticmethod
    def static_name() -> str:
        return _('T1 Cover page')

    @classmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        from plugins.ffe.print_documents.ffe_options import (
            FFEWriterPrintOption,
            FFEChiefArbiterPrintOption,
        )

        return FFETournamentsDocumentType.get_valid_option_types() + [
            FFEWriterPrintOption,
            FFEChiefArbiterPrintOption,
        ]

    @cached_property
    def chief_arbiter(self) -> Account | None:
        from plugins.ffe.print_documents.ffe_options import FFEChiefArbiterPrintOption

        if account_id := self.ffe_document._get_option(
            FFEChiefArbiterPrintOption
        ).value:
            return self.event.accounts_by_id[account_id]
        else:
            return None

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
            'chief_arbiter': self.chief_arbiter,
            'pairing': self.tournaments_pairing,
            'tie_breaks': self.tournaments_tie_breaks,
            'fide_player_count': self.tournaments_fide_players_count,
            'total_player_count': self.tournaments_total_players_count,
            'prizes_total': f'{self.tournaments_prizes_total:.2f}',
            'prizes_sharing': self.tournaments_prizes_sharing_systems,
        }


class FFET2Type(FFETournamentsDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t2-tournament-report'

    @staticmethod
    def static_name() -> str:
        return _('T2 Minutes')


class FFEArbiterCompensationType(FFETournamentsDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-arbiter-compensation'

    @staticmethod
    def static_name() -> str:
        return _('Arbitration compensation')

    @classmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        from plugins.ffe.print_documents.ffe_options import (
            FFEArbiterPrintOption,
        )

        return FFETournamentsDocumentType.get_valid_option_types() + [
            FFEArbiterPrintOption,
        ]

    @cached_property
    def arbiter(self) -> Account | None:
        from plugins.ffe.print_documents.ffe_options import FFEArbiterPrintOption

        if account_id := self.ffe_document._get_option(FFEArbiterPrintOption).value:
            return self.event.accounts_by_id[account_id]
        else:
            return None


class FFETournamentDocumentType(FFEDocumentType, ABC):
    @cached_property
    def tournament(self) -> Tournament:
        return self.ffe_document.tournament

    @property
    def tournaments(self) -> list[Tournament]:
        return [
            self.tournament,
        ]

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
    @cached_property
    def players(self) -> list[TournamentPlayer]:
        return []

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'players': self.players,
        }


class FFET3T4Type(FFEPlayersDocumentType, ABC):
    @classmethod
    def get_template_stem(cls) -> str:
        return 'ffe_t3_t4_players_licence'

    @classmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        from data.print_documents.options import TournamentPrintOption
        from plugins.ffe.print_documents.ffe_options import FFEDocumentTypePrintOption

        return [
            FFEDocumentTypePrintOption,
            TournamentPrintOption,
            cls.players_print_option(),
        ]

    @staticmethod
    @abstractmethod
    def players_print_option() -> type['FFENoLicencePlayersPrintOption']:
        """Returns the type of the option used."""

    @staticmethod
    @abstractmethod
    def ffe_licence() -> PlayerFFELicence:
        """Returns the FFE licence concerned."""

    @staticmethod
    @abstractmethod
    def ffe_form_number() -> int:
        """Returns the FFE form number concerned."""

    @cached_property
    def players(self) -> list[TournamentPlayer]:
        if player_ids := self.ffe_document._get_option(
            self.players_print_option()
        ).value:
            return [
                self.tournament.tournament_players_by_id[player_id]
                for player_id in player_ids
            ]
        else:
            return self.players_print_option().get_tournament_players(self.tournament)

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'ffe_licence': self.ffe_licence(),
            'ffe_form_number': self.ffe_form_number(),
        }


class FFET3Type(FFET3T4Type):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t3-players-licence'

    @staticmethod
    def static_name() -> str:
        return _('T3 Licence A certificate')

    @staticmethod
    def players_print_option() -> type['FFENoLicencePlayersPrintOption']:
        from plugins.ffe.print_documents import ffe_options

        return ffe_options.FFET3NoLicencePlayersPrintOption

    @staticmethod
    def ffe_licence() -> PlayerFFELicence:
        return PlayerFFELicence.A

    @staticmethod
    def ffe_form_number() -> int:
        return 3


class FFET4Type(FFET3T4Type):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t4-players-licence'

    @staticmethod
    def static_name() -> str:
        return _('T4 Licence B certificate')

    @staticmethod
    def players_print_option() -> type['FFENoLicencePlayersPrintOption']:
        from plugins.ffe.print_documents import ffe_options

        return ffe_options.FFET4NoLicencePlayersPrintOption

    @staticmethod
    def ffe_licence() -> PlayerFFELicence:
        return PlayerFFELicence.B

    @staticmethod
    def ffe_form_number() -> int:
        return 4


class FFEPlayerDocumentType(FFETournamentDocumentType, ABC):
    @classmethod
    def get_valid_option_types(cls) -> list[type[PrintOption]]:
        from data.print_documents.options import (
            TournamentPrintOption,
        )
        from plugins.ffe.print_documents.ffe_options import (
            FFEDocumentTypePrintOption,
            FFEWriterPrintOption,
        )

        return [
            FFEDocumentTypePrintOption,
            FFEWriterPrintOption,
            TournamentPrintOption,
            cls.player_print_option(),
        ]

    @staticmethod
    @abstractmethod
    def player_print_option() -> type[PrintOption]:
        """Returns the player option to use."""

    @property
    @abstractmethod
    def player(self) -> TournamentPlayer | None:
        """Returns the selected player."""

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'player': self.player,
        }


class FFEMandatoryPlayerDocumentType(FFEPlayerDocumentType, ABC):
    @staticmethod
    def player_print_option() -> type[PrintOption]:
        from data.print_documents.options import MandatoryPlayerPrintOption

        return MandatoryPlayerPrintOption

    @property
    def player(self) -> TournamentPlayer:
        return self.ffe_document.mandatory_player


class FFEOptionalPlayerDocumentType(FFEPlayerDocumentType, ABC):
    @staticmethod
    def player_print_option() -> type[PrintOption]:
        from data.print_documents.options import OptionalPlayerPrintOption

        return OptionalPlayerPrintOption

    @property
    def player(self) -> TournamentPlayer | None:
        return self.ffe_document.optional_player


class FFET5Type(FFEMandatoryPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t5-player-forfeit'

    @staticmethod
    def static_name() -> str:
        return _('T5 Unjustified forfeit investigation')

    @property
    def response_date(self) -> str:
        return (datetime.now() + timedelta(days=2)).strftime('%d/%m/%Y')

    @property
    def player_last_forfeit_round(self) -> str:
        for round_ in range(self.player.tournament.rounds, 0, -1):
            if self.player.pairings[round_].paired:
                if self.player.pairings[round_].forfeit_loss:
                    return str(round_)
                break
        return ''

    def template_context(
        self,
        ffe_document: 'FFEPrintDocument',
    ) -> dict[str, Any]:
        return super().template_context(ffe_document) | {
            'response_date': self.response_date,
            'player_last_forfeit_round': self.player_last_forfeit_round,
        }


class FFET6Type(FFEMandatoryPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t6-player-exclusion'

    @staticmethod
    def static_name() -> str:
        return _('T6 Player exclusion')


class FFET7Type(FFEMandatoryPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-t7-player-reporting'

    @staticmethod
    def static_name() -> str:
        return _('T7 Player reporting')


class FFECheatingType(FFEOptionalPlayerDocumentType):
    @staticmethod
    def static_id() -> str:
        return 'ffe-cheating'

    @staticmethod
    def static_name() -> str:
        return _('Cheating complaint')
