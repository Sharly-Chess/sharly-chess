from typing import TYPE_CHECKING, override

from packaging.version import Version

from common.i18n import _
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.event.event_store import StoredTournament
from plugins import PLUGINS_DIR
from plugins.fra.fra_schools import PLUGIN_NAME
from plugins.ffe.ffe_database import FfeDatabase
from plugins.fra.fra_schools.fra_schools_controller import FRASchoolsController
from plugins.fra.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra.fra_schools.utils import FRASchoolsPlayerPluginData
from plugins.ffe.ffe import FfePlugin
from plugins.hookspec import hookimpl
from plugins.manager import Path
from plugins.utils import (
    Plugin,
    PluginData,
    PluginUtils,
)
from web.controllers.base_controller import BaseController

if TYPE_CHECKING:
    from database.sqlite.event.event_store import StoredTournament


class FRASchoolsPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('French School Competitions')

    @property
    def dependencies(self) -> list[type[Plugin]]:
        return [FfePlugin]

    @property
    def description(self) -> str:
        return _('Adds support for school competitions in France')

    @property
    def version(self) -> Version:
        return Version('0.1.1')

    @override
    @property
    def templates_path(self) -> Path:
        return PLUGINS_DIR / 'fra' / self.id / 'templates'

    @override
    @property
    def federation(self) -> str | None:
        return 'FRA'

    def used_by_stored_tournament(self, stored_tournament: StoredTournament) -> bool:
        # TODO
        return False

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [
            FRASchoolsController,
        ]

    # ---------------------------------------------------------------------------------
    # Input-Output
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_local_source_databases(self, databases: list[type[LocalSourceDatabase]]):
        schools: type[LocalSourceDatabase] = FRASchoolsDatabase
        ffe: type[LocalSourceDatabase] = FfeDatabase
        PluginUtils.insert_on_equals(databases, schools, ffe, True)

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_player_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, FRASchoolsPlayerPluginData

    # @hookimpl
    # def get_player_admin_template_context(
    #     self, web_context: PlayerAdminWebContext
    # ) -> dict[str, Any]:
    #     assert web_context.admin_event is not None
    #     admin_event: 'Event' = web_context.admin_event

    #     # The leagues that will be shown on the league select list
    #     players_leagues: list[str] = sorted(
    #         {
    #             FFEUtils.get_player_plugin_data(player).league or ''
    #             for player in web_context.admin_event.players_by_id.values()
    #         }
    #     )

    #     # The leagues that will be selected on the league select list and used to filter the players
    #     filter_leagues: list[str] = [
    #         league
    #         for league in FFESessionHandler.get_session_admin_players_filter_leagues(
    #             web_context.request
    #         )
    #         if league in players_leagues
    #     ]

    #     # The licences that will be shown on the licence select list
    #     players_licences: list[PlayerFFELicence] = sorted(
    #         {
    #             FFEUtils.get_player_plugin_data(player).ffe_licence
    #             for player in admin_event.players_by_id.values()
    #         }
    #     )
    #     # The licences that will be selected on the licence select list and used to filter the players
    #     filter_licences: list[PlayerFFELicence] = (
    #         FFESessionHandler.get_session_admin_players_filter_licences(
    #             web_context.request
    #         )
    #     )

    #     league_counts: Counter[str | None] = Counter[str | None]()
    #     for player in web_context.admin_event.players_by_id.values():
    #         league_counts[FFEUtils.get_player_plugin_data(player).league] += 1

    #     licence_counts: Counter[PlayerFFELicence] = Counter[PlayerFFELicence]()
    #     for player in web_context.admin_event.players_by_id.values():
    #         licence_counts[FFEUtils.get_player_plugin_data(player).ffe_licence] += 1

    #     return {
    #         'admin_players_leagues': players_leagues,
    #         'admin_filter_leagues': filter_leagues,
    #         'admin_players_licences': players_licences,
    #         'admin_filter_licences': filter_licences,
    #         'ffe_league_counts': league_counts,
    #         'ffe_licence_counts': licence_counts,
    #         'admin_players_filter_leagues': FFESessionHandler.get_session_admin_players_filter_leagues(
    #             web_context.request
    #         ),
    #         'admin_players_filter_licences': FFESessionHandler.get_session_admin_players_filter_licences(
    #             web_context.request
    #         ),
    #     }

    @hookimpl
    def get_player_form_fields_template(self) -> str:
        return '/fra_schools_player_form_fields.html'

    # @hookimpl
    # def validate_player_form_fields(
    #     self,
    #     action: str,
    #     tournament: 'Tournament',
    #     data: dict[str, str],
    #     errors: dict[str, str],
    # ):
    #     league: str | None = WebContext.form_data_to_str(data, field := 'ffe_league')
    #     if league and league not in self.FFE_LEAGUES:
    #         # should never happen, not translated.
    #         errors[field] = f'Invalid league value [{data[field]}].'
    #         data[field] = ''
    #     if tournament:
    #         # When adding a player, the tournament may not be chosen (in this case do not test)
    #         try:
    #             ffe_id = WebContext.form_data_to_int(data, field := 'ffe_id', minimum=1)
    #             ffe_ids = [
    #                 FFEUtils.get_player_plugin_data(player).ffe_id
    #                 for player in tournament.players_by_id.values()
    #             ]

    #             if action == 'create' and ffe_id and ffe_id in ffe_ids:
    #                 errors[field] = _(
    #                     'The player with FFE ID [{ffe_id}] already '
    #                     'plays tournament [{tournament}].'
    #                 ).format(ffe_id=ffe_id, tournament=tournament.name)
    #         except ValueError:
    #             errors[field] = _('Invalid FFE ID [{ffe_id}].').format(
    #                 ffe_id=data[field]
    #             )
    #     try:
    #         if value := WebContext.form_data_to_int(data, field := 'ffe_licence'):
    #             PlayerFFELicence(value)
    #     except ValueError:
    #         errors[field] = f'Invalid FFE licence [{data[field]}].'

    #     ffe_licence_number: str | None = WebContext.form_data_to_str(
    #         data, field := 'ffe_licence_number'
    #     )
    #     if ffe_licence_number:
    #         if not re.match(r'^[A-Z]\d{5}$', ffe_licence_number):
    #             errors[field] = _(
    #                 'Invalid FFE licence number [{ffe_licence_number}].'
    #             ).format(ffe_licence_number=data[field])
    #         elif tournament:
    #             # When adding a player, the tournament may not be chosen (in this case do not test)
    #             ffe_licence_numbers = [
    #                 FFEUtils.get_player_plugin_data(player).ffe_licence_number
    #                 for player in tournament.players_by_id.values()
    #             ]
    #             if action == 'create' and ffe_licence_number in ffe_licence_numbers:
    #                 errors[field] = _(
    #                     'The player with FFE licence number '
    #                     '[{ffe_licence_number}] already plays '
    #                     'tournament [{tournament}].'
    #                 ).format(
    #                     ffe_licence_number=ffe_licence_number,
    #                     tournament=tournament.name,
    #                 )

    # @hookimpl
    # def get_extra_player_columns(self) -> Iterable[ExtraAdminColumn]:
    #     return [
    #         ExtraAdminColumn(
    #             at='club',
    #             header_template='/ffe_player_league_header.html',
    #             cell_template='/ffe_player_league_cell.html',
    #         ),
    #         ExtraAdminColumn(
    #             at='owed',
    #             header_template='/ffe_player_licence_header.html',
    #             cell_template='/ffe_player_licence_cell.html',
    #         ),
    #     ]

    # @hookimpl
    # def player_filters(
    #     self,
    #     web_context: PlayerAdminWebContext,
    #     template_context: dict[str, Any],
    # ) -> list[Callable[[Player], bool]]:
    #     filter_leagues: list[str] = (
    #         FFESessionHandler.get_session_admin_players_filter_leagues(
    #             web_context.request
    #         )
    #     )
    #     filter_licences: list[PlayerFFELicence] = (
    #         FFESessionHandler.get_session_admin_players_filter_licences(
    #             web_context.request
    #         )
    #     )

    #     admin_players_leagues = template_context['admin_players_leagues']
    #     admin_players_licences = template_context['admin_players_licences']
    #     filters: list[Callable[[Player], bool]] = []
    #     if len(filter_leagues) not in (0, len(admin_players_leagues)):
    #         filters.append(
    #             lambda player: FFEUtils.get_player_plugin_data(player).league
    #             in filter_leagues
    #         )
    #     if len(filter_licences) not in (0, len(admin_players_licences)):
    #         filters.append(
    #             lambda player: FFEUtils.get_player_plugin_data(player).ffe_licence
    #             in filter_licences
    #         )
    #     return filters

    # @hookimpl
    # def clear_player_filters(self, request: HTMXRequest):
    #     FFESessionHandler.set_session_admin_players_filter_leagues(request, [])
    #     FFESessionHandler.set_session_admin_players_filter_licences(request, [])

    # @hookimpl
    # def player_club_sort_key(self, player: Player):
    #     # We sort by league first
    #     return (
    #         FFEUtils.get_player_plugin_data(player).league or '',
    #         player.club,
    #         player.last_name,
    #         player.first_name,
    #     )

    # @hookimpl
    # def get_extra_players_datasheet_columns(self) -> Iterable[ExtraColumn]:
    #     return [
    #         ExtraColumn(
    #             at='tournament',
    #             title='ffe_id',
    #             value=lambda player: str(
    #                 FFEUtils.get_player_plugin_data(player).ffe_id or ''
    #             ),
    #         ),
    #         ExtraColumn(
    #             at='tournament',
    #             title='ffe_licence_number',
    #             value=lambda player: (
    #                 FFEUtils.get_player_plugin_data(player).ffe_licence_number or ''
    #             ),
    #         ),
    #         ExtraColumn(
    #             at='tournament',
    #             title='ffe_licence',
    #             value=lambda player: (
    #                 FFEUtils.get_player_plugin_data(player).ffe_licence.short_name
    #             ),
    #         ),
    #         ExtraColumn(
    #             at='club',
    #             title='league',
    #             value=lambda player: (
    #                 FFEUtils.get_player_plugin_data(player).league or ''
    #             ),
    #         ),
    #     ]
