import copy
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from types import ModuleType
from typing import Any, TYPE_CHECKING, Iterable, Optional

from litestar.plugins.htmx import HTMXRequest
from packaging.version import Version

from common import TEST_ENV, DEVEL_ENV
from common.i18n import _, ngettext
from common.exception import SharlyChessException
from data.columns import player_table, player_datasheet
from data.columns.player_datasheet import DatasheetColumn
from data.columns.player_table import TournamentPlayerTableColumn, ColumnUsage
from data.criteria.player_filter_options import PlayerFilterOption, ClubsFilterOption
from data.criteria.player_filters import PlayerFilter, ClubPlayerFilter
from data.input_output import DataSource, TournamentExporter, TournamentImporter
from data.input_output.data_source import FideDataSource
from data.pairings.managers import PairingVariationManager
from data.pairings.variations import SwissVariation
from data.player import Player, PlayerRating, PlayerRatingAndType, TournamentPlayer
from data.player_categories import PlayerCategory, JuniorCategory
from data.print_documents import PlayerSplitter, PrintDocument
from data.print_documents.documents import StatisticsPrintDocument
from data.print_documents.place_cards.data import PlaceCardPlayer
from data.print_documents.player_splitters import ClubPlayerSplitter
from data.print_documents.qrcode_types import QRCodeType
from data.tie_breaks import TieBreak, TieBreakOption
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.fide.fide_database import FideDatabase
from database.sqlite.local_source_database import LocalSourceDatabase
from plugins.ffe import migrations, PLUGIN_NAME, ffe_tie_breaks
from plugins.ffe.ffe_background_uploader import (
    EventLoader,
    FfeBackgroundUploader,
    FfeUploadStatus,
)
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_entity import (
    FFESiteQRCodeType,
    FfeLocalDataSource,
    LeaguePlayerSplitter,
    NicoisSwissVariation,
    FfeLeaguePlayerFilter,
    FfeLicencePlayerFilter,
    FfeLicenceFilterOption,
    FfeOnlineDataSource,
    FfeLeaguesFilterOption,
    FfeLeagueTableColumn,
    FfeIdDatasheetColumn,
    FfeLicenceNumberDatasheetColumn,
    FfeLicenceDatasheetColumn,
    FfeLeagueDatasheetColumn,
    FfeLicenceTypeTableColumn,
)
from plugins.ffe.ffe_event_controller import FfeAdminEventController
from plugins.ffe.ffe_report_documents import (
    FFEEventReportPrintDocument,
    FFEPlayersLicenceAPrintDocument,
    FFEPlayersLicenceBPrintDocument,
    FFEPlayerForfeitPrintDocument,
    FFEPlayerExclusionPrintDocument,
    FFEPlayerReportingPrintDocument,
)
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.ffe_sql_server import FFESqlServer
from plugins.ffe.ffe_tie_breaks import (
    BasePapiTieBreak,
    PapiBuchholzTypeOption,
)
from plugins.ffe.ffe_tournament_controller import FfeAdminTournamentController
from plugins.ffe.ffe_tournament_exporters import PapiTournamentExporter
from plugins.ffe.ffe_tournament_importers import (
    PapiJsonTournamentImporter,
    PapiTournamentImporter,
)
from plugins.ffe.papi_converter import PapiConverter, PapiPlayer
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.ffe.utils import (
    FFE_DEFAULT_UPLOAD_DELAY,
    FFE_MIN_UPLOAD_DELAY,
    FfeEventPluginData,
    FfePlayerPluginData,
    FfeTournamentPluginData,
)
from plugins.hookspec import ExtraAdminColumn, hookimpl, hookspec
from plugins.migration import PluginMigrationManager
from plugins.pairing_acceleration.pairing_acceleration import PairingAccelerationPlugin
from plugins.utils import (
    ExtraStatisticsSection,
    NavUploadItem,
    Plugin,
    PluginUtils,
    PluginData,
)
from utils.enum import (
    PlayerRatingType,
    Result,
    TournamentRating,
)
from web.controllers.admin.player_admin_controller import PlayerAdminWebContext
from web.controllers.base_controller import BaseController, WebContext

if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import StoredEvent
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


class FfePluginHooks:
    @hookspec
    def update_papi_player(
        self, papi_player: PapiPlayer, tournament_player: TournamentPlayer
    ):
        """Called when a player is converted to Papi format"""

    @hookspec
    def augment_stored_player_on_papi_import(
        self,
        event: 'Event',
        importer: TournamentImporter,
        stored_player: StoredPlayer,
    ):
        """Augment player data when fetched from Papi."""


class FfePlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Fédération Française des Échecs')

    @property
    def dependencies(self) -> list[type[Plugin]]:
        return [PairingAccelerationPlugin]

    @property
    def description(self) -> str:
        return _(
            'French Federation specific features (player search, results uploading, leagues, Papi import/export...)'
        )

    @property
    def version(self) -> Version:
        return Version('0.1.1')

    @property
    def hookspecs(self) -> type | None:
        return FfePluginHooks

    @property
    def default_is_enabled(self) -> bool:
        return True

    @property
    def default_event_is_enabled(self) -> bool:
        return True

    @property
    def federation(self) -> str | None:
        return 'FRA'

    @property
    def base_migration_module(self) -> ModuleType:
        return migrations

    @property
    def event_form_fields_template(self) -> str:
        return '/ffe_event_form_fields.html'

    def used_by_stored_tournament(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ) -> bool:
        ffe_data = stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        if ffe_data.get('ffe_id', None):
            return True
        for stored_tie_break in stored_tournament.stored_tie_breaks:
            if any(
                stored_tie_break.type == tie_break_type.static_id()
                for tie_break_type in self._tie_break_types
            ):
                return True
        if stored_tournament.pairing == NicoisSwissVariation.static_id():
            return True
        return False

    # The FFE league names.
    FFE_LEAGUES: dict[str, str] = {
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
    def get_event_migration_manager(
        self, event_database: EventDatabase
    ) -> PluginMigrationManager:
        return self.get_migration_manager(event_database)

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [
            FfeAdminEventController,
            FfeAdminTournamentController,
        ]

    @hookimpl
    def get_base_admin_template_context(self) -> dict[str, Any]:
        return {
            'ffe_auth_valid': '',
            'FFE_DEFAULT_UPLOAD_DELAY': FFE_DEFAULT_UPLOAD_DELAY,
        }

    # ---------------------------------------------------------------------------------
    # Input-Output
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_data_sources(self, data_sources: list[type[DataSource]]):
        local: type[DataSource] = FfeLocalDataSource
        online: type[DataSource] = FfeOnlineDataSource
        fide: type[DataSource] = FideDataSource
        PluginUtils.insert_on_equals(data_sources, online, fide, False)
        PluginUtils.insert_on_equals(data_sources, local, fide, False)

    @hookimpl
    def insert_local_source_databases(self, databases: list[type[LocalSourceDatabase]]):
        ffe: type[LocalSourceDatabase] = FfeDatabase
        fide: type[LocalSourceDatabase] = FideDatabase
        PluginUtils.insert_on_equals(databases, ffe, fide, False)

    @hookimpl
    def insert_tournament_exporters(self, exporters: list[type[TournamentExporter]]):
        exporters.append(PapiTournamentExporter)

    @hookimpl
    def insert_tournament_importers(self, importers: list[type[TournamentImporter]]):
        importers.append(PapiTournamentImporter)
        if TEST_ENV or DEVEL_ENV:
            importers.append(PapiJsonTournamentImporter)

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_player_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, FfePlayerPluginData

    @hookimpl
    def get_player_admin_template_context(
        self, web_context: PlayerAdminWebContext
    ) -> dict[str, Any]:
        request = web_context.request
        allowed_players = web_context.client.allowed_players

        # The leagues that will be shown on the league select list
        players_leagues: list[str] = sorted(
            {
                FFEUtils.get_player_plugin_data(player).league or ''
                for player in allowed_players
            }
        )

        # The leagues that will be selected on the league select list and used to filter the players
        filter_leagues: list[str] = [
            league
            for league in FFESessionHandler.get_session_admin_players_filter_leagues(
                request
            )
            if league in players_leagues
        ]

        # The licences that will be shown on the licence select list
        players_licences: list[PlayerFFELicence] = sorted(
            {
                FFEUtils.get_player_plugin_data(player).ffe_licence
                for player in allowed_players
            }
        )
        # The licences that will be selected on the licence select list and used to filter the players
        filter_licences: list[PlayerFFELicence] = (
            FFESessionHandler.get_session_admin_players_filter_licences(
                web_context.request
            )
        )
        league_counts: Counter[str] = Counter[str]()
        for player in allowed_players:
            league_counts[FFEUtils.get_player_plugin_data(player).league or ''] += 1

        licence_counts: Counter[PlayerFFELicence] = Counter[PlayerFFELicence]()
        for player in allowed_players:
            licence_counts[FFEUtils.get_player_plugin_data(player).ffe_licence] += 1
        return {
            'admin_players_leagues': players_leagues,
            'admin_filter_leagues': filter_leagues,
            'admin_players_licences': players_licences,
            'admin_filter_licences': filter_licences,
            'ffe_league_counts': league_counts,
            'ffe_licence_counts': licence_counts,
            'admin_players_filter_leagues': FFESessionHandler.get_session_admin_players_filter_leagues(
                request
            ),
            'admin_players_filter_licences': FFESessionHandler.get_session_admin_players_filter_licences(
                request
            ),
        }

    @hookimpl
    def get_player_form_template_context(
        self, web_context: 'PlayerAdminWebContext'
    ) -> dict[str, Any]:
        return {
            'licence_options': {
                str(licence.value): licence.compact_name for licence in PlayerFFELicence
            },
            'ffe_league_options': {'': '-'}
            | {code: f'{code} - {name}' for code, name in self.FFE_LEAGUES.items()},
        }

    @hookimpl
    def insert_player_form_fields_template(
        self, templates_by_section: defaultdict[str, list[str]]
    ):
        templates_by_section['identity'].insert(
            0, '/ffe_player_form_identity_fields.html'
        )
        templates_by_section['fide'].append('/ffe_player_form_fields.html')

    @hookimpl
    def validate_player_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        player: 'Player',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        league: str | None = WebContext.form_data_to_str(data, field := 'ffe_league')
        if league and league not in self.FFE_LEAGUES:
            # should never happen, not translated.
            errors[field] = f'Invalid league value [{data[field]}].'
            data[field] = ''
        if tournament:
            # When adding a player, the tournament may not be chosen (in this case do not test)
            try:
                ffe_id = WebContext.form_data_to_int(data, field := 'ffe_id', minimum=1)
                ffe_ids = [
                    FFEUtils.get_player_plugin_data(p).ffe_id
                    for p in tournament.tournament_players_by_id.values()
                    if not player or p.id != player.id
                ]

                if ffe_id and ffe_id in ffe_ids:
                    errors[field] = _(
                        'The player with FFE ID [{ffe_id}] already '
                        'plays tournament [{tournament}].'
                    ).format(ffe_id=ffe_id, tournament=tournament.name)
            except ValueError:
                errors[field] = _('Invalid FFE ID [{ffe_id}].').format(
                    ffe_id=data[field]
                )
        try:
            if value := WebContext.form_data_to_int(data, field := 'ffe_licence'):
                PlayerFFELicence(value)
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
                # When adding a player, the tournament may not be chosen (in this case do not test)
                ffe_licence_numbers = [
                    FFEUtils.get_player_plugin_data(p).ffe_licence_number
                    for p in tournament.tournament_players_by_id.values()
                    if not player or p.id != player.id
                ]
                if ffe_licence_number in ffe_licence_numbers:
                    errors[field] = _(
                        'The player with FFE licence number '
                        '[{ffe_licence_number}] already plays '
                        'tournament [{tournament}].'
                    ).format(
                        ffe_licence_number=ffe_licence_number,
                        tournament=tournament.name,
                    )

    @hookimpl
    async def augment_player_after_search(
        self, stored_player: StoredPlayer, data_source: DataSource
    ):
        if data_source.id in (
            FfeOnlineDataSource.static_id(),
            FfeLocalDataSource.static_id(),
        ):
            return
        # Try to get more information by requesting the FFE SQL server
        fide_id = stored_player.fide_id
        if not fide_id:
            return
        ffe_stored_player: StoredPlayer | None = None
        try:
            # Try to get more information by requesting the FFE database
            async with FFESqlServer() as ffe_sql_server:
                ffe_stored_player = await ffe_sql_server.get_stored_player_by_fide_id(
                    fide_id
                )
        except SharlyChessException:
            if (ffe_database := FfeDatabase()).exists():
                # Try to get more information by requesting the FFE database
                with ffe_database:
                    ffe_stored_player = ffe_database.get_stored_player_by_fide_id(
                        fide_id
                    )
        if ffe_stored_player:
            for rating_type in TournamentRating:
                stored_rating = stored_player.ratings.get(rating_type.value, None)
                rating = (
                    PlayerRating.from_stored_value(stored_rating)
                    if stored_rating
                    else None
                )
                ffe_stored_rating = ffe_stored_player.ratings.get(
                    rating_type.value, None
                )
                if ffe_stored_rating:
                    ffe_rating = PlayerRating.from_stored_value(ffe_stored_rating)
                    augmented_rating = PlayerRating(
                        fide=rating.fide
                        if rating and rating.fide is not None
                        else ffe_rating.fide,
                        national=rating.national
                        if rating and rating.national is not None
                        else ffe_rating.national,
                        estimated=rating.estimated
                        if rating and rating.estimated is not None
                        else ffe_rating.estimated,
                    )
                    stored_player.ratings[rating_type.value] = (
                        augmented_rating.stored_value
                    )
            if not stored_player.date_of_birth or (
                ffe_stored_player.date_of_birth
                and (
                    not stored_player.year_of_birth
                    or stored_player.year_of_birth
                    == ffe_stored_player.date_of_birth.year
                )
            ):
                stored_player.date_of_birth = ffe_stored_player.date_of_birth
                stored_player.year_of_birth = None
            stored_player.comment = ffe_stored_player.comment
            stored_player.club = ffe_stored_player.club
            stored_player.plugin_data[self.id] = copy.copy(
                ffe_stored_player.plugin_data.get(self.id, {})
            )

    @hookimpl
    def augment_place_card_player(
        self,
        tournament_player: TournamentPlayer,
        place_card_player: PlaceCardPlayer,
    ):
        setattr(
            place_card_player,
            'ffe_league',
            FFEUtils.get_player_plugin_data(tournament_player).league,
        )

    @hookimpl
    def get_player_rating(
        self,
        tournament_rating: TournamentRating,
        player_rating_type: PlayerRatingType,
        player: 'Player',
        category: 'PlayerCategory',
    ) -> Optional[PlayerRatingAndType]:
        # In France, regardless of the player_rating_type of the tournament,
        # the FIDE rating is used, if available, falling back to the national rating
        ratings = player.ratings[tournament_rating]
        if ratings.fide is not None:
            return PlayerRatingAndType(ratings.fide, PlayerRatingType.FIDE)
        if ratings.national is not None:
            return PlayerRatingAndType(ratings.national, PlayerRatingType.NATIONAL)
        if ratings.estimated is not None:
            return PlayerRatingAndType(ratings.estimated, PlayerRatingType.ESTIMATED)
        if tournament_rating == TournamentRating.STANDARD:
            if isinstance(category, JuniorCategory):
                value = 1299
            else:
                value = 1399
        else:
            value = 1199
            if isinstance(category, JuniorCategory):
                if category.age_limit <= 10:
                    value = 799
                elif category.age_limit <= 14:
                    value = 999
        return PlayerRatingAndType(value, PlayerRatingType.ESTIMATED)

    @hookimpl
    def is_tournament_participation_possible(
        self, tournament: 'Tournament', tournament_player: TournamentPlayer
    ) -> str | None:
        plugin_data = FFEUtils.get_player_plugin_data(tournament_player)
        ffe_licence_number = plugin_data.ffe_licence_number
        ffe_id = plugin_data.ffe_id
        if ffe_licence_number and any(
            FFEUtils.get_player_plugin_data(tournament_player_).ffe_licence_number
            == ffe_licence_number
            for tournament_player_ in tournament.tournament_players_by_id.values()
        ):
            return _(
                'FFE licence [{ffe_licence_number}] already '
                'present in tournament [{tournament}].'
            ).format(
                ffe_licence_number=ffe_licence_number,
                tournament=tournament.name,
            )

        if ffe_id and any(
            FFEUtils.get_player_plugin_data(tournament_player_).ffe_id == ffe_id
            for tournament_player_ in tournament.tournament_players_by_id.values()
        ):
            # This string is not translated because the error should never happen
            return (
                f'FFE ID [{ffe_id}] already present in tournament [{tournament.name}].'
            )

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
                lambda player: (FFEUtils.get_player_plugin_data(player).league or '')
                in filter_leagues
            )
        if len(filter_licences) not in (0, len(admin_players_licences)):
            filters.append(
                lambda player: FFEUtils.get_player_plugin_data(player).ffe_licence
                in filter_licences
            )
        return filters

    @hookimpl
    def clear_player_filters(self, request: HTMXRequest):
        FFESessionHandler.set_session_admin_players_filter_leagues(request, [])
        FFESessionHandler.set_session_admin_players_filter_licences(request, [])

    @hookimpl
    def player_sort_key(self, player: Player, sort_type: str):
        if sort_type == 'club':
            # We sort by league first
            return (
                FFEUtils.get_player_plugin_data(player).league or '',
                player.club,
                player.last_name,
                player.first_name,
            )
        return None

    @hookimpl
    def insert_player_datasheet_columns(self, datasheet_columns: list[DatasheetColumn]):
        tournament: type[DatasheetColumn] = player_datasheet.TournamentColumn
        ffe_columns: list[DatasheetColumn] = [
            FfeIdDatasheetColumn(),
            FfeLicenceNumberDatasheetColumn(),
            FfeLicenceDatasheetColumn(),
        ]
        for column in ffe_columns:
            PluginUtils.insert_on_isinstance(
                datasheet_columns, column, tournament, after=False
            )
        federation: type[DatasheetColumn] = player_datasheet.FederationColumn
        PluginUtils.insert_on_isinstance(
            datasheet_columns, FfeLeagueDatasheetColumn(), federation
        )

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

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def on_event_duplicated(self, event_database: EventDatabase):
        stored_tournaments = event_database.load_stored_tournaments()
        for stored_tournament in stored_tournaments:
            old_plugin_data = FfeTournamentPluginData.from_stored_value(
                stored_tournament.plugin_data.get(PLUGIN_NAME, {})
            )

            # Only retain the auto_upload setting
            new_plugin_data = FfeTournamentPluginData(
                auto_upload=old_plugin_data.auto_upload
            )
            stored_tournament.plugin_data[PLUGIN_NAME] = (
                new_plugin_data.to_stored_value()
            )
            event_database.update_stored_tournament(stored_tournament)

    @hookimpl
    def get_event_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, FfeEventPluginData

    @hookimpl
    def validate_event_form_fields(
        self,
        action: str,
        event: 'Event | None',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        federation = WebContext.form_data_to_str(data, field := 'federation')
        if federation != 'FRA':
            # We only validate FFE fields for the FRA federation
            return

        ffe_auto_upload_delay = WebContext.form_data_to_int(
            data, field := 'ffe_auto_upload_delay'
        )
        if ffe_auto_upload_delay and ffe_auto_upload_delay < FFE_MIN_UPLOAD_DELAY:
            errors[field] = _(
                'The delay must be at least {min_delay} minutes to avoid overloading the FFE server.'
            ).format(min_delay=FFE_MIN_UPLOAD_DELAY)

    @hookimpl
    def get_default_prize_currency(self) -> str:
        return 'EUR'

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, FfeTournamentPluginData

    @hookimpl
    def on_tournament_data_updated(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ):
        # This hook being called in most database writes, it needs to be optimized
        if not FfeBackgroundUploader.should_schedule_tournament_upload(
            stored_event, stored_tournament
        ):
            return
        event = EventLoader().load_event(stored_event.uniq_id)
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        tournament = event.tournaments_by_id[tournament_id]
        FfeBackgroundUploader.schedule_upload(tournament)

    @hookimpl
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        ffe_auto_upload_options: dict[str, str] = {
            '': '',
            WebContext.value_to_form_data(False): _('Disabled'),
        } | {
            WebContext.value_to_form_data(True): _('Enabled'),
        }
        event_auto_upload = FFEUtils.get_event_plugin_data(event).auto_upload
        ffe_auto_upload_options[''] = _('Use default - {option}').format(
            option=ffe_auto_upload_options[
                WebContext.value_to_form_data(event_auto_upload)
            ]
        )

        return (
            '/ffe_tournament_form_fields.html',
            {
                'ffe_auto_upload_options': ffe_auto_upload_options,
            },
        )

    @hookimpl
    def validate_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament | None',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        try:
            WebContext.form_data_to_int(data, 'ffe_id')
        except ValueError:
            errors['ffe_id'] = _('The FFE ID is a positive integer.')
        ffe_password = WebContext.form_data_to_str(data, 'ffe_password')
        if ffe_password and not re.match('^[A-Z]{10}$', ffe_password):
            errors['ffe_password'] = _(
                'The password of the tournament on the FFE website is made of 10 uppercase letters.'
            )

    @hookimpl
    def get_tournament_page_template_context(self) -> dict[str, Any]:
        return {'ffe_utils': FFEUtils}

    @hookimpl
    def get_tournament_card_connexion_template(
        self, tournament: 'Tournament'
    ) -> str | None:
        if not FFEUtils.get_tournament_plugin_data(tournament).ffe_id:
            return None
        return '/ffe_tournament_card_connexion.html'

    @hookimpl
    def get_tournament_card_action_menu_items_template(self) -> str:
        return '/ffe_tournament_card_action_menu_items.html'

    @hookimpl
    def get_tournament_tie_breaks_warning_message(
        self, tournament: 'Tournament'
    ) -> str | None:
        if not FFEUtils.get_tournament_plugin_data(tournament).ffe_id:
            return None
        return PapiConverter.check_tiebreaks_warning(tournament.tie_breaks)

    @hookimpl
    def get_tournament_pairing_warning_message(
        self, tournament: 'Tournament'
    ) -> str | None:
        if not FFEUtils.get_tournament_plugin_data(tournament).ffe_id:
            return None
        return PapiConverter.check_pairing_warning(tournament)

    @hookimpl
    def signal_tournament_set(
        self, event: 'Event', stored_tournament: 'StoredTournament'
    ) -> str | None:
        if blocker := PapiConverter.check_rounds(stored_tournament.rounds):
            return blocker
        pairing_variation = PairingVariationManager(event).get_object(
            stored_tournament.pairing
        )
        if warning := PapiConverter.check_pairing_variation_warning(pairing_variation):
            return warning
        return None

    @hookimpl
    def signal_special_result_set(
        self, tournament: 'Tournament', result: Result
    ) -> str | None:
        return PapiConverter.check_result(result, tournament)

    # ---------------------------------------------------------------------------------
    # Upload
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_nav_upload_items(self, event: 'Event') -> Iterable[NavUploadItem]:
        has_upload_error = False
        statuses = FfeBackgroundUploader.upload_status_messages
        tournaments = event.tournaments
        for tournament in tournaments:
            result = statuses.get(
                FfeBackgroundUploader.result_id(event.uniq_id, tournament.id),
                None,
            )
            if result and result.status == FfeUploadStatus.ERROR:
                has_upload_error = True
                break

        return [
            NavUploadItem(
                key='ffe_upload',
                title=_('FFE'),
                icon_path='/images/ffe.png',
                modal_route_name='ffe-upload-modal',
                has_upload_error=has_upload_error,
            )
        ]

    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_print_document(self, print_documents: list[type['PrintDocument']]):
        for c in [
            FFEEventReportPrintDocument,
            FFEPlayersLicenceAPrintDocument,
            FFEPlayersLicenceBPrintDocument,
            FFEPlayerForfeitPrintDocument,
            FFEPlayerExclusionPrintDocument,
            FFEPlayerReportingPrintDocument,
        ]:
            PluginUtils.insert_last(print_documents, c)  # type: ignore

    @hookimpl
    def alter_print_and_screen_player_columns(
        self,
        usage: ColumnUsage,
        player_columns: list['TournamentPlayerTableColumn'],
    ):
        PluginUtils.insert_on_isinstance(
            player_columns,
            FfeLeagueTableColumn(usage),
            player_table.FederationColumn,
        )
        PluginUtils.insert_on_isinstance(
            player_columns,
            FfeLicenceTypeTableColumn(usage),
            player_table.PaidColumn,
            after=False,
        )

    @hookimpl
    def insert_print_player_splitter_types(
        self, player_splitter_types: list[type[PlayerSplitter]]
    ):
        lps: type[PlayerSplitter] = LeaguePlayerSplitter
        cps: type[PlayerSplitter] = ClubPlayerSplitter
        PluginUtils.insert_on_equals(player_splitter_types, lps, cps)

    @hookimpl
    def insert_print_qrcode_types(self, qrcode_types: list[type[QRCodeType]]):
        qrcode_types.append(FFESiteQRCodeType)

    @hookimpl
    def get_extra_statistics_sections(
        self, document: PrintDocument, tournaments: list['Tournament']
    ) -> Iterable[ExtraStatisticsSection]:
        if isinstance(document, StatisticsPrintDocument):
            counter = Counter[str](
                league
                for tournament in tournaments
                for p in tournament.tournament_players
                if (league := FFEUtils.get_player_plugin_data(p).league) is not None
            )

            if not counter:
                return []

            items: list[tuple[str, int]] = list(counter.items())
            items = sorted(items, key=lambda item: (-item[1], item[0]))
            rows = {k: v for k, v in items}

            return [
                ExtraStatisticsSection(
                    at='club',
                    title=_('Leagues'),
                    rows=rows,
                    subtitle=ngettext(
                        '{count} league represented',
                        '{count} leagues represented',
                        len(rows),
                    ).format(count=len(rows)),
                )
            ]
        return []

    # ---------------------------------------------------------------------------------
    # Tie breaks
    # ---------------------------------------------------------------------------------

    @property
    def _tie_break_types(self) -> list[type[BasePapiTieBreak]]:
        return [
            ffe_tie_breaks.PapiBuchholzTieBreak,
            ffe_tie_breaks.PapiPerformanceTieBreak,
            ffe_tie_breaks.PapiSumOfBuchholzTieBreak,
            ffe_tie_breaks.PapiKashdanTieBreak,
        ]

    @hookimpl
    def insert_tie_break_types(self, tie_break_types: list[type[TieBreak]]):
        for tie_break_type in self._tie_break_types:
            PluginUtils.insert_on_equals(
                tie_break_types, tie_break_type, tie_break_type.base_tie_break_type()
            )

    @hookimpl
    def insert_tie_break_option_types(
        self, tie_break_option_types: list[type[TieBreakOption]]
    ):
        tie_break_option_types.append(PapiBuchholzTypeOption)

    # ---------------------------------------------------------------------------------
    # Pairings
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_swiss_pairing_variation_types(
        self, variation_types: list[type[SwissVariation]]
    ):
        variation_types.append(NicoisSwissVariation)

    # ---------------------------------------------------------------------------------
    # Prizes
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_player_filter_types(
        self, player_filter_types: list[type['PlayerFilter']]
    ):
        league: type[PlayerFilter] = FfeLeaguePlayerFilter
        club: type[PlayerFilter] = ClubPlayerFilter
        PluginUtils.insert_on_equals(player_filter_types, league, club)
        player_filter_types.append(FfeLicencePlayerFilter)

    @hookimpl
    def insert_player_filter_option_types(
        self, player_filter_option_types: list[type['PlayerFilterOption']]
    ):
        licence: type[PlayerFilterOption] = FfeLicenceFilterOption
        league: type[PlayerFilterOption] = FfeLeaguesFilterOption
        club: type[PlayerFilterOption] = ClubsFilterOption
        PluginUtils.insert_on_equals(player_filter_option_types, league, club)
        player_filter_option_types.append(licence)
