import re

from collections import Counter
from collections.abc import Callable

from datetime import datetime
from decimal import Decimal
from types import ModuleType
from typing import Any, TYPE_CHECKING, Iterable, Optional, override

from litestar.plugins.htmx import HTMXRequest
from dateutil.relativedelta import relativedelta
from packaging.version import Version

from common.i18n import _
from common.network import NetworkMonitor
from data.input_output import PlayerUpdater
from data.pairings.variations import SwissVariation
from data.print_documents import PlayerSplitter, PrintDocument
from data.print_documents.documents import PlayerPrintDocument
from data.print_documents.player_splitters import ClubPlayerSplitter
from data.tie_breaks import TieBreak
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.utils import FFE_DEFAULT_UPLOAD_DELAY, FFE_MIN_UPLOAD_DELAY
from plugins.ffe.ffe_tournament_controller import FfeAdminTournamentController
from utils.enum import PlayerCategory, PlayerRatingType, ScreenType, TournamentRating
from data.player import Player, PlayerRating
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.local_source_database import LocalSourceDatabase
from plugins.ffe import migrations, PLUGIN_NAME, ffe_tie_breaks
from plugins.ffe.engine.ffe_engine import FFEEngine
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_entity import (
    FfePlayerUpdater,
    LeaguePlayerSplitter,
    NicoisSwissVariation,
)
from plugins.ffe.ffe_event_controller import FfeAdminEventController
from plugins.ffe.ffe_search_controller import FfeSearchController
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.ffe_tie_breaks import papi_performance_bonus
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.hookspec import ExtraAdminColumn, hookimpl, ExtraColumn
from plugins.migration import PluginMigrationManager
from plugins.utils import Plugin, PluginEngineArgument, PluginNavBarItem, PluginUtils

from web.controllers.admin.player_admin_controller import PlayerAdminWebContext
from web.controllers.base_controller import BaseController, WebContext


if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import StoredEvent
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


class FfePlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return 'FFE'

    @property
    def description(self) -> str:
        return _(
            'French Federation specific features (player search, leagues, Papi compatibility)'
        )

    @property
    def version(self) -> Version:
        return Version('0.1.1')

    @override
    @property
    def default_is_enabled(self) -> bool:
        return True

    @override
    @property
    def is_state_editable(self) -> bool:
        return False

    @override
    @property
    def base_migration_module(self) -> ModuleType:
        return migrations

    # The FFE league names.
    FFE_LEAGUES: dict[str, str] = {
        '': '',
        'ARA': 'Auvergne-Rhône-Alpes',
        'BFC': 'Bourgogne-Franche-Comté',
        'BRE': 'Bretagne',
        'CRS': 'Corse',
        'CVL': 'Centre-Val de Loire',
        'EST': 'Grand-Est',
        'GUA': 'Guadeloupe',
        'GUY': 'Guyane',
        'HDF': 'Hauts-de-France',
        'IDF': 'Île-de-France',
        'MAR': 'Martinique',
        'NAQ': 'Nouvelle-Aquitaine',
        'NCA': 'Nouvelle-Calédonie',
        'NOR': 'Normandie',
        'OCC': 'Occitanie',
        'PAC': "Provence-Alpes-Côte d'azur",
        'PDL': 'Pays de la Loire',
        'POL': 'Saint-Pierre-et-Miquelon',
        'REU': 'Réunion',
    }

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @hookimpl
    def on_init(self):
        FfeDatabase().check()

    @hookimpl
    def get_event_migration_manager(
        self, event_database: EventDatabase
    ) -> PluginMigrationManager:
        return self.get_migration_manager(event_database)

    @hookimpl
    def get_controllers(self) -> Iterable[type[BaseController]]:
        return [
            FfeSearchController,
            FfeAdminEventController,
            FfeAdminTournamentController,
        ]

    @hookimpl
    def get_base_admin_template_context(self) -> dict[str, Any]:
        return {
            'ffe_search_available': FfeDatabase().exists()
            or NetworkMonitor.connected(),
            'ffe_leagues': self.FFE_LEAGUES,
            'ffe_auth_valid': '',
        }

    @hookimpl
    def get_engine_argument(self) -> PluginEngineArgument:
        return PluginEngineArgument('f', 'ffe', 'run the FFE utilities', FFEEngine)

    # ---------------------------------------------------------------------------------
    # Data sources
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_local_source_database_types(
        self, database_types: list[type[LocalSourceDatabase]]
    ):
        database_types.append(FfeDatabase)

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_db_player_fields(self) -> list[str]:
        return ['RefFFE', 'AffType', 'NrFFE', 'Ligue']

    @hookimpl
    def augment_player_after_db_fetch(self, player: Player, row: dict[str, Any]):
        if not player.plugin_data:
            player.plugin_data = {}
        player.plugin_data[self.id] = {
            'ffe_id': row['RefFFE'],
            'ffe_licence': PlayerFFELicence.from_papi_value(row['AffType'] or ''),
            'ffe_licence_number': row['NrFFE'] or '',
            'league': row['Ligue'] or '',
        }

    @hookimpl
    def player_data_for_db_write(self, player: Player) -> dict[str, Any]:
        pd = player.plugin_data
        return {
            'RefFFE': self.get_data(
                pd,
                'ffe_id',
                (datetime.now() - relativedelta(years=30)),  # like Papi does :-(
            ),
            'AffType': (
                self.get_data(pd, 'ffe_licence').to_papi_value
                if self.get_data(pd, 'ffe_licence')
                else ''
            ),
            'NrFFE': self.get_data(pd, 'ffe_licence_number', None),
            'Ligue': self.get_data(pd, 'league', ''),
        }

    @hookimpl
    def get_player_admin_template_context(
        self, web_context: PlayerAdminWebContext
    ) -> dict[str, Any]:
        assert web_context.admin_event is not None
        admin_event: 'Event' = web_context.admin_event

        # The leagues that will be shown on the league select list
        players_leagues: list[str] = sorted(
            {
                self.get_data(player.plugin_data, 'league')
                for player in web_context.admin_event.players_by_id.values()
            }
        )

        # The leagues that will be selected on the league select list and used to filter the players
        filter_leagues: list[str] = [
            league
            for league in FFESessionHandler.get_session_admin_players_filter_leagues(
                web_context.request
            )
            if league in players_leagues
        ]

        # The licences that will be shown on the licence select list
        players_licences: list[PlayerFFELicence] = sorted(
            {
                self.get_data(player.plugin_data, 'ffe_licence')
                for player in admin_event.players_by_id.values()
            }
        )
        # The licences that will be selected on the licence select list and used to filter the players
        filter_licences: list[PlayerFFELicence] = (
            FFESessionHandler.get_session_admin_players_filter_licences(
                web_context.request
            )
        )

        league_counts: Counter[str] = Counter[str]()
        for player in web_context.admin_event.players_by_id.values():
            league_counts[self.get_data(player.plugin_data, 'league')] += 1

        licence_counts: Counter[PlayerFFELicence] = Counter[PlayerFFELicence]()
        for player in web_context.admin_event.players_by_id.values():
            licence_counts[self.get_data(player.plugin_data, 'ffe_licence')] += 1

        return {
            'admin_players_leagues': players_leagues,
            'admin_filter_leagues': filter_leagues,
            'admin_players_licences': players_licences,
            'admin_filter_licences': filter_licences,
            'ffe_league_counts': league_counts,
            'ffe_licence_counts': licence_counts,
            'admin_players_filter_leagues': FFESessionHandler.get_session_admin_players_filter_leagues(
                web_context.request
            ),
            'admin_players_filter_licences': FFESessionHandler.get_session_admin_players_filter_licences(
                web_context.request
            ),
        }

    @hookimpl
    def get_player_search_template(self) -> str:
        return '/ffe_search.html'

    @hookimpl
    def get_player_form_fields_template(self) -> str:
        return '/ffe_player_form_fields.html'

    @hookimpl
    def get_player_form_data(
        self, plugin_data: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            'ffe_licence': WebContext.value_to_form_data(
                self.get_data(plugin_data, 'ffe_licence', None)
            ),
            'ffe_licence_number': WebContext.value_to_form_data(
                self.get_data(plugin_data, 'ffe_licence_number', None)
            ),
            'ffe_id': WebContext.value_to_form_data(
                self.get_data(plugin_data, 'ffe_id', None)
            ),
            'ffe_league': WebContext.value_to_form_data(
                self.get_data(plugin_data, 'league', None)
            ),
        }

    @hookimpl
    def get_validated_player_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        league: str | None = WebContext.form_data_to_str(data, field := 'ffe_league')
        if league and league not in self.FFE_LEAGUES:
            # should never happen, not translated.
            errors[field] = f'Invalid league value [{data[field]}].'
            data[field] = ''
        ffe_id: int | None = None

        if tournament:
            # When adding a player, the tournament may not be chosen (in this case do not test)
            try:
                ffe_id = WebContext.form_data_to_int(data, field := 'ffe_id', minimum=1)
                ffe_ids = [
                    self.get_data(player.plugin_data, 'ffe_id', None)
                    for player in tournament.players_by_id.values()
                ]

                if action == 'create' and ffe_id and ffe_id in ffe_ids:
                    errors[field] = _(
                        'The player with FFE ID [{ffe_id}] already '
                        'plays tournament [{tournament_uniq_id}].'
                    ).format(ffe_id=ffe_id, tournament_uniq_id=tournament.uniq_id)
            except ValueError:
                errors[field] = _('Invalid FFE ID [{ffe_id}].').format(
                    ffe_id=data[field]
                )
        ffe_licence: PlayerFFELicence = PlayerFFELicence.NONE
        try:
            if value := WebContext.form_data_to_int(data, field := 'ffe_licence'):
                ffe_licence = PlayerFFELicence(value)
        except ValueError:
            errors[field] = f'Invalid FFE licence [{data[field]}].'

        ffe_licence_number: str | None = WebContext.form_data_to_str(
            data, field := 'ffe_licence_number'
        )
        if ffe_licence_number:
            if not re.match(r'^[A-Z]\d{5}$', ffe_licence_number):
                errors[field] = _(
                    'Invalid FFE licence number [{ffe_licence_number}].'
                ).format(ffe_licence_number=data[field])
            elif tournament:
                # When adding a player, the tournament may not me chosen (in this case do not test)
                ffe_licence_numbers = [
                    player.plugin_data.get(self.id, {}).get('ffe_licence_number')
                    for player in tournament.players_by_id.values()
                ]
                if action == 'create' and ffe_licence_number in ffe_licence_numbers:
                    errors[field] = _(
                        'The player with FFE licence number '
                        '[{ffe_licence_number}] already plays '
                        'tournament [{tournament_uniq_id}].'
                    ).format(
                        ffe_licence_number=ffe_licence_number,
                        tournament_uniq_id=tournament.uniq_id,
                    )

        return {
            self.id: {
                'ffe_id': ffe_id,
                'ffe_licence': ffe_licence,
                'ffe_licence_number': ffe_licence_number,
                'league': league,
            }
        }

    @hookimpl
    def augment_player_after_search(self, player: Player):
        # Try to get more information by requesting the FFE database
        if player.fide_id and (ffe_database := FfeDatabase()).exists():
            with ffe_database:
                if ffe_player := ffe_database.get_player_by_fide_id(player.fide_id):
                    for rating_type in [
                        TournamentRating.STANDARD,
                        TournamentRating.RAPID,
                        TournamentRating.BLITZ,
                    ]:
                        rating = player.get_rating(rating_type)
                        if rating.type == PlayerRatingType.ESTIMATED:
                            player.ratings[rating_type] = ffe_player.ratings[
                                rating_type
                            ]
                    if (
                        ffe_player.date_of_birth
                        and player.year_of_birth == ffe_player.year_of_birth
                    ):
                        player.date_of_birth = ffe_player.date_of_birth
                    player.comment = ffe_player.comment
                    player.club = ffe_player.club
                    data = ffe_player.plugin_data
                    player.plugin_data[self.id] = {
                        'ffe_id': self.get_data(data, 'ffe_id'),
                        'ffe_licence': self.get_data(data, 'ffe_licence'),
                        'ffe_licence_number': self.get_data(data, 'ffe_licence_number'),
                        'league': self.get_data(data, 'league'),
                    }

    @hookimpl
    def set_player_default_ratings(self, federation: str, player: 'Player'):
        if federation != 'FRA':
            return

        def set_rating(tournament_rating: TournamentRating, rating_value: int):
            player.ratings[tournament_rating] = PlayerRating(
                rating_value, PlayerRatingType.ESTIMATED
            )

        if not player.get_rating(TournamentRating.RAPID).value:
            match player.category:
                case PlayerCategory.U8 | PlayerCategory.U10:
                    set_rating(TournamentRating.RAPID, 799)
                case PlayerCategory.U12 | PlayerCategory.U14:
                    set_rating(TournamentRating.RAPID, 999)
                case _:
                    set_rating(TournamentRating.RAPID, 1199)
        if not player.get_rating(TournamentRating.BLITZ).value:
            match player.category:
                case PlayerCategory.U8 | PlayerCategory.U10:
                    set_rating(TournamentRating.BLITZ, 799)
                case PlayerCategory.U12 | PlayerCategory.U14:
                    set_rating(TournamentRating.BLITZ, 999)
                case _:
                    set_rating(TournamentRating.BLITZ, 1199)
        if not player.get_rating(TournamentRating.STANDARD).value:
            match player.category:
                case (
                    PlayerCategory.U8
                    | PlayerCategory.U10
                    | PlayerCategory.U12
                    | PlayerCategory.U14
                    | PlayerCategory.U16
                    | PlayerCategory.U18
                    | PlayerCategory.U20
                ):
                    set_rating(TournamentRating.STANDARD, 1299)
                case _:
                    set_rating(TournamentRating.STANDARD, 1399)

    @hookimpl
    def is_tournament_participation_possible(
        self, tournament: 'Tournament', player: Player
    ) -> str | None:
        ffe_licence_number = player.plugin_data.get(self.id, {}).get(
            'ffe_licence_number', None
        )
        ffe_id = self.get_data(player.plugin_data, 'ffe_id', None)
        if ffe_licence_number and any(
            self.get_data(player_.plugin_data, 'ffe_licence_number', None)
            == ffe_licence_number
            for player_ in tournament.players_by_id.values()
        ):
            return _(
                'FFE licence [{ffe_licence_number}] already '
                'present in tournament [{tournament_uniq_id}].'
            ).format(
                ffe_licence_number=self.get_data(
                    player.plugin_data, 'ffe_licence_number', None
                ),
                tournament_uniq_id=tournament.uniq_id,
            )

        if ffe_id and any(
            self.get_data(player_.plugin_data, 'ffe_id', None) == ffe_id
            for player_ in tournament.players_by_id.values()
        ):
            # This string is not translated because the error should never happen
            return f'FFE ID [{ffe_id}] already present in tournament [{tournament.uniq_id}].'

        return None

    @hookimpl
    def get_extra_player_columns(self) -> Iterable[ExtraAdminColumn]:
        return [
            ExtraAdminColumn(
                at='club',
                header_template='/ffe_player_league_header.html',
                cell_template='/ffe_player_league_cell.html',
            ),
            ExtraAdminColumn(
                at='owed',
                header_template='/ffe_player_licence_header.html',
                cell_template='/ffe_player_licence_cell.html',
            ),
        ]

    @hookimpl
    def player_filters(
        self,
        web_context: PlayerAdminWebContext,
        template_context: dict[str, Any],
    ) -> list[Callable[[Player], bool]]:
        filter_leagues: list[str] = (
            FFESessionHandler.get_session_admin_players_filter_leagues(
                web_context.request
            )
        )
        filter_licences: list[PlayerFFELicence] = (
            FFESessionHandler.get_session_admin_players_filter_licences(
                web_context.request
            )
        )

        admin_players_leagues = template_context['admin_players_leagues']
        admin_players_licences = template_context['admin_players_licences']
        filters: list[Callable[[Player], bool]] = []
        if len(filter_leagues) not in (0, len(admin_players_leagues)):
            filters.append(
                lambda player: self.get_data(player.plugin_data, 'league')
                in filter_leagues
            )
        if len(filter_licences) not in (0, len(admin_players_licences)):
            filters.append(
                lambda player: self.get_data(player.plugin_data, 'ffe_licence')
                in filter_licences
            )
        return filters

    @hookimpl
    def clear_player_filters(self, request: HTMXRequest):
        FFESessionHandler.set_session_admin_players_filter_leagues(request, [])
        FFESessionHandler.set_session_admin_players_filter_licences(request, [])

    @hookimpl
    def player_club_sort_key(self, player: Player):
        # We sort by league first
        return (
            self.get_data(player.plugin_data, 'league'),
            player.club,
            player.last_name,
            player.first_name,
        )

    @hookimpl
    def get_extra_players_datasheet_columns(self) -> Iterable[ExtraColumn]:
        return [
            ExtraColumn(
                at='tournament',
                title='ffe_id',
                value=lambda player: self.get_data(player.plugin_data, 'ffe_id'),
            ),
            ExtraColumn(
                at='tournament',
                title='ffe_licence_number',
                value=lambda player: self.get_data(
                    player.plugin_data, 'ffe_licence_number'
                ),
            ),
            ExtraColumn(
                at='tournament',
                title='ffe_licence',
                value=lambda player: self.get_data(
                    player.plugin_data, 'ffe_licence'
                ).short_name,
            ),
            ExtraColumn(
                at='club',
                title='league',
                value=lambda player: self.get_data(player.plugin_data, 'league'),
            ),
        ]

    @hookimpl
    def get_extra_players_update_columns(self) -> Iterable[ExtraAdminColumn]:
        return [
            ExtraAdminColumn(
                at='fide_id',
                header_template='/ffe_players_update/licence_number_header.html',
                cell_template='/ffe_players_update/licence_number_cell.html',
            ),
            ExtraAdminColumn(
                at='fide_id',
                header_template='/ffe_players_update/licence_header.html',
                cell_template='/ffe_players_update/licence_cell.html',
            ),
            ExtraAdminColumn(
                at='club',
                header_template='/ffe_players_update/league_header.html',
                cell_template='/ffe_players_update/league_cell.html',
            ),
        ]

    @hookimpl
    def insert_player_updater_types(self, updater_types: list[type[PlayerUpdater]]):
        updater_types.append(FfePlayerUpdater)

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def augment_event_after_db_fetch(
        self, stored_event: 'StoredEvent', row: dict[str, Any]
    ):
        if not stored_event.plugin_data:
            stored_event.plugin_data = {}
        stored_event.plugin_data[self.id] = {
            'ffe_auto_upload': row.get('ffe_auto_upload', False),
            'ffe_auto_upload_delay': row.get('ffe_auto_upload_delay', None),
        }

    @hookimpl
    def event_data_for_db_write(self, stored_event: 'StoredEvent') -> dict[str, Any]:
        td = stored_event.plugin_data
        return {
            'ffe_auto_upload': int(self.get_data(td, 'ffe_auto_upload')),
            'ffe_auto_upload_delay': self.get_data(td, 'ffe_auto_upload_delay'),
        }

    @hookimpl
    def get_event_info_rows_template(self) -> str:
        return '/ffe_event_info_rows.html'

    @hookimpl
    def get_event_card_block_template(self) -> str:
        return '/ffe_event_card_block.html'

    @hookimpl
    def get_event_form_fields_template(self) -> str:
        return '/ffe_event_form_fields.html'

    @hookimpl
    def get_event_form_data(self, event: Optional['Event']) -> dict[str, Any]:
        if not event:
            return {
                'ffe_auto_upload': 'off',
                'ffe_auto_upload_delay': '',
                'ffe_default_delay': FFE_DEFAULT_UPLOAD_DELAY,
            }

        return {
            'ffe_auto_upload': WebContext.value_to_form_data(
                bool(self.get_data(event.plugin_data, 'ffe_auto_upload', False))
            ),
            'ffe_auto_upload_delay': WebContext.value_to_form_data(
                self.get_data(event.plugin_data, 'ffe_auto_upload_delay', '')
            ),
            'ffe_default_delay': FFE_DEFAULT_UPLOAD_DELAY,
        }

    @hookimpl
    def get_validated_event_form_fields(
        self,
        action: str,
        event: 'Event | None',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        ffe_auto_upload = WebContext.form_data_to_bool(data, 'ffe_auto_upload')
        ffe_auto_upload_delay = WebContext.form_data_to_int(
            data, field := 'ffe_auto_upload_delay'
        )
        if ffe_auto_upload_delay and ffe_auto_upload_delay < FFE_MIN_UPLOAD_DELAY:
            errors[field] = _(
                f'The delay must be at least {FFE_MIN_UPLOAD_DELAY} minutes to avoid overloading the FFE server.'
            )

        # Keep data other than these two fields
        previous_data = event.plugin_data.get(self.id, {}) if event else {}

        return {
            self.id: previous_data
            | {
                'ffe_auto_upload': ffe_auto_upload or False,
                'ffe_auto_upload_delay': ffe_auto_upload_delay,
            }
        }

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def on_tournament_data_updated(self, tournament: 'Tournament'):
        if FFEUtils.resolve_auto_upload(tournament):
            FfeBackgroundUploader.schedule_upload(tournament)

    @hookimpl
    def augment_tournament_after_db_fetch(
        self, stored_tournament: 'StoredTournament', row: dict[str, Any]
    ):
        if not stored_tournament.plugin_data:
            stored_tournament.plugin_data = {}
        stored_tournament.plugin_data[self.id] = {
            'ffe_id': row.get('ffe_id', ''),
            'ffe_password': row.get('ffe_password', ''),
            'ffe_auto_upload': SQLiteDatabase.load_bool_or_none_from_database_field(
                row.get('ffe_auto_upload', None)
            ),
            'ffe_last_upload': row.get('ffe_last_upload', 0.0),
            'ffe_last_rules_upload': row.get('ffe_last_rules_upload', 0.0),
        }

    @hookimpl
    def tournament_data_for_db_write(
        self, stored_tournament: 'StoredTournament'
    ) -> dict[str, Any]:
        data = stored_tournament.plugin_data
        return {
            'ffe_id': self.get_data(data, 'ffe_id', None),
            'ffe_password': self.get_data(data, 'ffe_password', None),
            'ffe_auto_upload': self.get_data(data, 'ffe_auto_upload', None),
        }

    @hookimpl
    def on_tournament_init(self, tournament: 'Tournament'):
        data = tournament.stored_tournament.plugin_data
        if not self.get_data(data, 'ffe_id') or not self.get_data(data, 'ffe_password'):
            tournament.event.add_debug(
                _(
                    'Certification number and FFE password not set, '
                    'operations on the FFE website will not be available.'
                ),
                tournament=tournament,
            )

    @hookimpl
    def get_tournament_form_fields_template(self) -> str:
        return '/ffe_tournament_form_fields.html'

    @hookimpl
    def get_tournament_form_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> dict[str, Any]:
        ffe_auto_upload_options: dict[str, str] = {
            '': '',
            WebContext.value_to_form_data(False): _('Disabled'),
        } | {
            WebContext.value_to_form_data(True): _('Enabled'),
        }
        event_auto_upload = bool(
            self.get_data(event.plugin_data, 'ffe_auto_upload', False)
        )
        ffe_auto_upload_options[''] = _('By default - {option}').format(
            option=ffe_auto_upload_options[
                WebContext.value_to_form_data(event_auto_upload)
            ]
        )

        if not tournament:
            return {
                'ffe_id': '',
                'ffe_password': '',
                'ffe_auto_upload': '',
                'ffe_auto_upload_options': ffe_auto_upload_options,
            }

        return {
            'ffe_id': WebContext.value_to_form_data(
                self.get_data(tournament.plugin_data, 'ffe_id', None)
            ),
            'ffe_password': WebContext.value_to_form_data(
                self.get_data(tournament.plugin_data, 'ffe_password', None)
            ),
            'ffe_auto_upload': WebContext.value_to_form_data(
                self.get_data(tournament.plugin_data, 'ffe_auto_upload', None)
            ),
            'ffe_auto_upload_options': ffe_auto_upload_options,
        }

    @hookimpl
    def get_validated_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament | None',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        ffe_id = None
        try:
            ffe_id = WebContext.form_data_to_int(data, 'ffe_id')
        except ValueError:
            errors['ffe_id'] = _('The FFE ID is a positive integer.')
        ffe_password = WebContext.form_data_to_str(data, 'ffe_password')
        if ffe_password and not re.match('^[A-Z]{10}$', ffe_password):
            errors['ffe_password'] = _(
                'The password of the tournament on the FFE website is made of 10 uppercase letters.'
            )
        ffe_auto_upload = WebContext.form_data_to_bool(data, 'ffe_auto_upload')
        # Keep data other than these two fields (such as file upload times)
        previous_data = tournament.plugin_data.get(self.id, {}) if tournament else {}

        return {
            self.id: previous_data
            | {
                'ffe_id': ffe_id,
                'ffe_password': ffe_password,
                'ffe_auto_upload': ffe_auto_upload,
            }
        }

    @hookimpl
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        return (
            '/ffe_tournament_card_block.html',
            {
                'ffe_utils': FFEUtils,
            },
        )

    @hookimpl
    def get_tournament_card_menu_items_template(self) -> str:
        return '/ffe_tournament_action_items.html'

    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_print_player_splitter_types(
        self, player_splitter_types: list[type[PlayerSplitter]]
    ):
        lps: type[PlayerSplitter] = LeaguePlayerSplitter
        cps: type[PlayerSplitter] = ClubPlayerSplitter
        PluginUtils.insert_on_equals(player_splitter_types, lps, cps)

    @hookimpl
    def get_extra_print_view_columns(
        self, document: PrintDocument
    ) -> Iterable[ExtraColumn]:
        if isinstance(document, PlayerPrintDocument):
            return [
                ExtraColumn(
                    at='first-round' if document.is_crosstable else 'club',
                    title=_('League *** LEAGUE FOR PRINT VIEW'),
                    classes='center',
                    value=lambda player: self.get_data(player.plugin_data, 'league'),
                )
            ]
        return []

    @hookimpl
    def get_extra_print_view_css(self, document: PrintDocument) -> str:
        if isinstance(document, PlayerPrintDocument):
            return '.player-table .league { text-align: center; }'
        return ''

    # ---------------------------------------------------------------------------------
    # Nav bar
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_event_nav_bar_items_and_data(
        self, event: 'Event'
    ) -> tuple[Iterable[PluginNavBarItem], dict[str, Any]]:
        return (
            [PluginNavBarItem(at='database', template='/ffe_nav_buttons.html')],
            {},
        )

    # ---------------------------------------------------------------------------------
    # User screens
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_extra_screen_columns(self, screen: ScreenType) -> Iterable[ExtraColumn]:
        match screen:
            case ScreenType.RANKING:
                return [
                    ExtraColumn(
                        at='club',
                        title=_('League *** LEAGUE FOR PRINT VIEW'),
                        classes='center',
                        value=lambda player: self.get_data(
                            player.plugin_data, 'league'
                        ),
                    )
                ]

            case _:
                return []

    # ---------------------------------------------------------------------------------
    # Tie breaks
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_extra_tie_break_classes(self) -> list[type[TieBreak]]:
        return [
            ffe_tie_breaks.PapiStandardBuchholzTieBreak,
            ffe_tie_breaks.PapiBuchholzCutBottomTieBreak,
            ffe_tie_breaks.PapiMedianBuchholzTieBreak,
            ffe_tie_breaks.PapiPerformanceTieBreak,
            ffe_tie_breaks.PapiSumOfBuchholzTieBreak,
            ffe_tie_breaks.PapiKashdanTieBreak,
        ]

    # ---------------------------------------------------------------------------------
    # Pairings
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_swiss_pairing_variation_types(
        self, variation_types: list[type[SwissVariation]]
    ):
        variation_types.append(NicoisSwissVariation)

    # ---------------------------------------------------------------------------------
    # Shared utils
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_performance_bonus_function(self) -> Callable[[float], int | float]:
        return papi_performance_bonus

    @hookimpl
    def get_round_ranking_function(self) -> Callable[[float | Decimal], int]:
        return round
