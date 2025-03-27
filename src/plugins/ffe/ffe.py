import re

from collections import Counter
from collections.abc import Callable

from datetime import datetime
from decimal import Decimal
from functools import cached_property, partial
from typing import Any, TYPE_CHECKING, Iterable, override

from litestar.contrib.htmx.request import HTMXRequest
from dateutil.relativedelta import relativedelta
from packaging.version import Version

from common.exception import PapiWebException
from common.i18n import _
from common.network import NetworkMonitor
from data.event import Event
from data.input_output import AbstractPlayerUpdater, PlayerMatch, PlayerUpdaterField
from data.tie_break import AbstractTieBreak
from data.util import PlayerCategory, PlayerRatingType, ScreenType, TournamentRating
from data.player import Player
from data.print import (
    AbstractPlayerSplitter,
    ClubPlayerSplitter,
    AbstractPrintDocument,
    AbstractPlayerPrintDocument,
)
from plugins.ffe import migrations, ffe_tie_break, PLUGIN_NAME
from plugins.ffe.engine.ffe_engine import FFEEngine
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_event_controller import FfeAdminEventController
from plugins.ffe.ffe_search_controller import FfeSearchController
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.ffe_sql_server import FFESqlServer
from plugins.ffe.ffe_tie_break import papi_performance_bonus
from plugins.ffe.util import PlayerFFELicence
from plugins.hookspec import ExtraAdminColumn, hookimpl, ExtraColumn
from plugins.utils import (
    AbstractPlugin,
    PluginEngineArgument,
    PluginMigrationManager,
    PluginUtils,
)

from web.controllers.admin.player_admin_controller import PlayerAdminWebContext
from web.controllers.base_controller import BaseController, WebContext


if TYPE_CHECKING:
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfePlugin(AbstractPlugin):
    @property
    def id(self) -> str:
        return PLUGIN_NAME

    @property
    def name(self) -> str:
        return 'FFE'

    @property
    def description(self) -> str:
        return _(
            'French Federation specific features '
            '(player search, leagues, Papi compatibility)'
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
    @cached_property
    def migration_manager(self) -> PluginMigrationManager:
        return PluginMigrationManager(self, migrations)

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
    def get_event_migration_manager(self) -> PluginMigrationManager:
        return self.migration_manager

    @hookimpl
    def get_controllers(self) -> Iterable[type[BaseController]]:
        return [
            FfeSearchController,
            FfeAdminEventController,
        ]

    @hookimpl
    def get_base_admin_template_context(self) -> dict[str, Any]:
        return {
            'ffe_search_available': FfeDatabase().exists()
            or NetworkMonitor.connected(),
            'ffe_leagues': self.FFE_LEAGUES,
        }

    @hookimpl
    def get_engine_argument(self) -> PluginEngineArgument:
        return PluginEngineArgument('f', 'ffe', 'run the FFE utilities', FFEEngine)

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
        admin_event: Event = web_context.admin_event
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
            ffe_licence = PlayerFFELicence(
                WebContext.form_data_to_int(data, field := 'ffe_licence')
            )
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
        if FfeDatabase().exists():
            with FfeDatabase() as ffe_database:
                if ffe_player := ffe_database.get_player_by_fide_id(player.fide_id):
                    for rating_type in [
                        TournamentRating.STANDARD,
                        TournamentRating.RAPID,
                        TournamentRating.BLITZ,
                    ]:
                        if (
                            player.rating_types[rating_type]
                            == PlayerRatingType.ESTIMATED
                        ):
                            player.ratings[rating_type] = ffe_player.ratings[
                                rating_type
                            ]
                            player.rating_types[rating_type] = ffe_player.rating_types[
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

        if not player.ratings[TournamentRating.RAPID]:
            match player.category:
                case PlayerCategory.U8 | PlayerCategory.U10:
                    player.ratings[TournamentRating.RAPID] = 799
                case PlayerCategory.U12 | PlayerCategory.U14:
                    player.ratings[TournamentRating.RAPID] = 999
                case _:
                    player.ratings[TournamentRating.RAPID] = 1199
        if not player.ratings[TournamentRating.BLITZ]:
            match player.category:
                case PlayerCategory.U8 | PlayerCategory.U10:
                    player.ratings[TournamentRating.BLITZ] = 799
                case PlayerCategory.U12 | PlayerCategory.U14:
                    player.ratings[TournamentRating.BLITZ] = 999
                case _:
                    player.ratings[TournamentRating.BLITZ] = 1199
        if not player.ratings[TournamentRating.STANDARD]:
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
                    player.ratings[TournamentRating.STANDARD] = 1299
                case _:
                    player.ratings[TournamentRating.STANDARD] = 1399

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
    def filter_player(
        self,
        web_context: PlayerAdminWebContext,
        template_context: dict[str, Any],
        player: Player,
    ) -> bool:
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

        return (
            len(filter_leagues) in [0, len(admin_players_leagues)]
            or self.get_data(player.plugin_data, 'league') in filter_leagues
        ) and (
            len(filter_licences) in [0, len(admin_players_licences)]
            or self.get_data(player.plugin_data, 'ffe_licence') in filter_licences
        )

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

    class FfePlayerMatch(PlayerMatch):
        @cached_property
        def diff_field_ids(self) -> list[str] | None:
            if not self.match_player:
                return None
            diff_field_ids = super().diff_field_ids
            for field_id in ('league', 'ffe_licence'):
                if field_id in self.field_ids and get_data(
                    self.player.plugin_data, field_id
                ) != get_data(self.match_player.plugin_data, field_id):
                    diff_field_ids.append(field_id)
            return diff_field_ids

        @override
        def update_player_from_match(self, field_ids: list[str]):
            if not self.match_player:
                return
            super().update_player_from_match(field_ids)
            for field_id in ('league', 'ffe_licence'):
                if field_id in self.field_ids and get_data(
                    self.player.plugin_data, field_id
                ) != (match := get_data(self.match_player.plugin_data, field_id)):
                    self.player.plugin_data[PLUGIN_NAME][field_id] = match

    class FfePlayerUpdater(AbstractPlayerUpdater):
        @override
        @property
        def name(self) -> str:
            return _('FFE database')

        @override
        @property
        def id(self) -> str:
            return 'ffe'

        @override
        def fields(self) -> list[PlayerUpdaterField]:
            return (
                self._ratings_fields()
                + self._identity_fields()
                + self._federation_fields()
                + self._club_fields()
                + self._fide_fields()
            ) + [
                PlayerUpdaterField(_('League'), 'league'),
                PlayerUpdaterField(_('FFE licence number'), 'ffe_licence_number'),
                PlayerUpdaterField(_('FFE Licence'), 'ffe_licence'),
            ]

        @staticmethod
        def _get_ffe_licence_number(player) -> str | None:
            return get_data(player.plugin_data, 'ffe_licence_number')

        @override
        async def get_player_matches(
            self,
            players: list[Player],
            field_ids: list[str],
            diff_only: bool,
        ) -> list[PlayerMatch] | None:
            ffe_licence_numbers: list[str] = []
            for player in players:
                if ffe_licence_number := self._get_ffe_licence_number(player):
                    ffe_licence_numbers.append(ffe_licence_number)
            match_players: list[Player]
            try:
                async with FFESqlServer() as server:
                    match_players = [
                        player
                        async for player in await server.get_players_by_ffe_licence_number(
                            ffe_licence_numbers
                        )
                    ]
            except PapiWebException:
                database = FfeDatabase()
                if database.exists():
                    self.warning_message = _(
                        'Warning: connection to the online FFE database failed, '
                        'local database was used. Some data might be outdated '
                        '(last update on {date})'
                    ).format(date=database.updated_at.strftime('%d-%m-%Y'))
                    with database:
                        match_players = database.get_players_by_ffe_licence_number(
                            ffe_licence_numbers
                        )
                else:
                    return None
            return self._create_player_matches(
                players,
                match_players,
                lambda p1, p2: (
                    self._get_ffe_licence_number(p1)
                    and self._get_ffe_licence_number(p1)
                    == self._get_ffe_licence_number(p2)
                ),
                field_ids,
                diff_only,
                FfePlugin.FfePlayerMatch,
            )

    @hookimpl
    def get_player_updaters(self) -> list[AbstractPlayerUpdater]:
        return [self.FfePlayerUpdater()]

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def augment_tournament_after_db_fetch(
        self, stored_tournament: 'StoredTournament', row: dict[str, Any]
    ):
        if not stored_tournament.plugin_data:
            stored_tournament.plugin_data = {}
        stored_tournament.plugin_data[self.id] = {
            'ffe_id': row.get('ffe_id', ''),
            'ffe_password': row.get('ffe_password', ''),
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
            'ffe_last_upload': self.get_data(data, 'ffe_last_upload', 0.0),
            'ffe_last_rules_upload': self.get_data(data, 'ffe_last_rules_upload', 0.0),
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
        self, tournament: 'Tournament | None'
    ) -> dict[str, Any]:
        if not tournament:
            return {'ffe_id': '', 'ffe_password': ''}

        return {
            'ffe_id': WebContext.value_to_form_data(
                self.get_data(tournament.plugin_data, 'ffe_id', None)
            ),
            'ffe_password': WebContext.value_to_form_data(
                self.get_data(tournament.plugin_data, 'ffe_password', None)
            ),
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

        # Keep data other than these two fields (such as file upload times)
        previous_data = tournament.plugin_data.get(self.id, {}) if tournament else {}

        return {
            self.id: previous_data
            | {
                'ffe_id': ffe_id,
                'ffe_password': ffe_password,
            }
        }

    @hookimpl
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        return ('/ffe_tournament_card_block.html', {})

    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------

    class LeaguePlayerSplitter(AbstractPlayerSplitter):
        @property
        def id(self) -> str:
            return 'ffe_league'

        @property
        def name(self) -> str:
            return _('League')

        @staticmethod
        def get_split_key(player: Player) -> str:
            return PluginUtils.get_plugin_data(
                PLUGIN_NAME, player.plugin_data, 'league', ''
            )

    @hookimpl
    def insert_print_player_splitters(
        self, player_splitters: list['AbstractPlayerSplitter']
    ):
        PluginUtils.insert_on_isinstance(
            player_splitters, self.LeaguePlayerSplitter(), ClubPlayerSplitter
        )

    @hookimpl
    def get_extra_print_view_columns(
        self, document: AbstractPrintDocument
    ) -> Iterable[ExtraColumn]:
        if isinstance(document, AbstractPlayerPrintDocument):
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
    def get_extra_print_view_css(self, document: AbstractPrintDocument) -> str:
        if isinstance(document, AbstractPlayerPrintDocument):
            return '.player-table .league { text-align: center; }'
        return ''

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
    def get_extra_tie_break_classes(self) -> list[type[AbstractTieBreak]]:
        return [
            ffe_tie_break.PapiBuchholzTieBreak,
            ffe_tie_break.PapiBuchholzCutBottomTieBreak,
            ffe_tie_break.PapiMedianBuchholzTieBreak,
            ffe_tie_break.PapiPerformanceTieBreak,
            ffe_tie_break.PapiSumOfBuchholzTieBreak,
            ffe_tie_break.PapiKashdanTieBreak,
        ]


# ---------------------------------------------------------------------------------
# Shared utils
# ---------------------------------------------------------------------------------


@hookimpl
def get_performance_bonus_function() -> Callable[[float], int | float]:
    return papi_performance_bonus


@hookimpl
def get_round_ranking_function() -> Callable[[float | Decimal], int]:
    return round
