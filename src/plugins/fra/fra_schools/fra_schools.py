from typing import TYPE_CHECKING, override

from packaging.version import Version

from common.i18n import _
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.event.event_store import StoredTournament
from plugins import PLUGINS_DIR
from plugins.fra.fra_schools import PLUGIN_NAME
from plugins.fra.fra_schools.fra_schools_controller import FRASchoolsController
from plugins.fra.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra.fra_schools.utils import FRASchoolsPlayerPluginData
from plugins.ffe.ffe import FfePlugin
from plugins.ffe.ffe_database import FfeDatabase
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
