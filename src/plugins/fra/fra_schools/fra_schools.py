from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Iterable, override

from packaging.version import Version

from litestar.plugins.htmx import HTMXRequest
from common.i18n import _
from data.columns.player_datasheet import DatasheetColumn
from data.event import Player
from data.print_documents import PlayerSplitter
from data.print_documents.player_splitters import ClubPlayerSplitter
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.event.event_store import StoredTournament
from data.columns import player_table, player_datasheet
from plugins import PLUGINS_DIR
from plugins.ffe.papi_converter import PapiPlayer
from plugins.fra.fra_schools import PLUGIN_NAME
from plugins.fra.fra_schools.fra_schools_controller import FRASchoolsController
from plugins.fra.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra.fra_schools.fra_schools_entity import (
    FraSchoolDatasheetColumn,
    FraSchoolPlayerSplitter,
    FraSchoolTableColumn,
)
from plugins.fra.fra_schools.fra_schools_event_controller import (
    FraSchoolsAdminEventController,
)
from plugins.fra.fra_schools.fra_schools_session_handler import FRASchoolsSessionHandler
from plugins.fra.fra_schools.utils import FRASchoolsPlayerPluginData, FRASchoolsUtils
from plugins.ffe.ffe import FfeLeagueTableColumn, FfePlugin
from plugins.ffe.ffe_database import FfeDatabase
from plugins.hookspec import ExtraAdminColumn, hookimpl
from plugins.manager import Path
from plugins.utils import (
    Plugin,
    PluginData,
    PluginUtils,
)
from web.controllers.admin.player_admin_controller import PlayerAdminWebContext
from web.controllers.base_controller import BaseController
from web.utils import PlayerColumn

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
        players = stored_tournament.stored_players
        for stored_player in players:
            data = stored_player.plugin_data.get(PLUGIN_NAME, {})
            if data.get('school_name', None) is not None:
                return True
        return False

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [
            FraSchoolsAdminEventController,
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

    @hookimpl
    def get_player_admin_template_context(
        self, web_context: PlayerAdminWebContext
    ) -> dict[str, Any]:
        assert web_context.admin_event is not None

        # The schools that will be shown on the school select list
        players_schools: list[str] = sorted(
            {
                FRASchoolsUtils.get_player_plugin_data(player).school_name or ''
                for player in web_context.admin_event.players_by_id.values()
            }
        )

        school_counts: Counter[str | None] = Counter[str | None]()
        for player in web_context.admin_event.players_by_id.values():
            school_counts[
                FRASchoolsUtils.get_player_plugin_data(player).school_name or ''
            ] += 1

        return {
            'fra_schools': players_schools,
            'fra_school_counts': school_counts,
            'fra_schools_filter': FRASchoolsSessionHandler.get_session_filter_schools(
                web_context.request
            ),
        }

    @hookimpl
    def get_player_form_fields_template(self) -> str:
        return '/fra_schools_player_form_fields.html'

    @hookimpl
    def get_extra_player_columns(self) -> Iterable[ExtraAdminColumn]:
        return [
            ExtraAdminColumn(
                at='yob',
                header_template='/fra_schools_player_school_header.html',
                cell_template='/fra_schools_player_school_cell.html',
            ),
        ]

    @hookimpl
    def player_filters(
        self,
        web_context: PlayerAdminWebContext,
        template_context: dict[str, Any],
    ) -> list[Callable[[Player], bool]]:
        filter_schools: list[str] = FRASchoolsSessionHandler.get_session_filter_schools(
            web_context.request
        )
        schools = template_context['fra_schools']
        filters: list[Callable[[Player], bool]] = []
        if len(filter_schools) not in (0, len(schools)):
            filters.append(
                lambda player: (
                    FRASchoolsUtils.get_player_plugin_data(player).school_name or ''
                )
                in filter_schools
            )
        return filters

    @hookimpl
    def clear_player_filters(self, request: HTMXRequest):
        FRASchoolsSessionHandler.set_session_filter_schools(request, [])

    @hookimpl
    def player_sort_key(self, player: 'Player', sort_type: str) -> tuple | None:
        if sort_type == 'fra_schools_school':
            return (
                FRASchoolsUtils.get_player_plugin_data(player).school_name or '',
                player.last_name,
                player.first_name or '',
            )
        return None

    @hookimpl
    def insert_player_datasheet_columns(self, datasheet_columns: list[DatasheetColumn]):
        club: type[DatasheetColumn] = player_datasheet.ClubColumn
        fra_school_columns: list[DatasheetColumn] = [
            FraSchoolDatasheetColumn(),
        ]
        for column in fra_school_columns:
            PluginUtils.insert_on_isinstance(
                datasheet_columns, column, club, after=True
            )

    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------

    @hookimpl
    def alter_print_document_player_columns(self, player_columns: list[PlayerColumn]):
        # Remove FederationColumn and LeagueColumn
        player_columns[:] = [
            col
            for col in player_columns
            if not isinstance(
                col, (player_table.FederationColumn, FfeLeagueTableColumn)
            )
        ]
        index = next(
            (
                i
                for i, column in enumerate(player_columns)
                if isinstance(column, player_table.ClubColumn)
            ),
            None,
        )
        if index is not None:
            player_columns[index] = FraSchoolTableColumn()

    @hookimpl
    def insert_print_player_splitter_types(
        self, player_splitter_types: list[type[PlayerSplitter]]
    ):
        lps: type[PlayerSplitter] = FraSchoolPlayerSplitter
        cps: type[PlayerSplitter] = ClubPlayerSplitter
        PluginUtils.replace_on_equals(player_splitter_types, lps, cps)

    # ---------------------------------------------------------------------------------
    # Plugin hooks
    # ---------------------------------------------------------------------------------

    @hookimpl
    def update_papi_player(self, papi_player: PapiPlayer, player: Player):
        papi_player.club = (
            FRASchoolsUtils.get_player_plugin_data(player).school_name or ''
        )
