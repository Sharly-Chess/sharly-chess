from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Iterable, override

from litestar.plugins.htmx import HTMXRequest
from packaging.version import Version

from common.i18n import _
from data.columns import player_table, player_datasheet
from data.columns.player_datasheet import DatasheetColumn
from data.columns.player_table import PlayerTableColumn, ColumnUsage
from data.criteria.player_filter_options import PlayerFilterOption, ClubsFilterOption
from data.criteria.player_filters import PlayerFilter, ClubPlayerFilter
from data.event import Player
from data.print_documents import PlayerSplitter
from data.print_documents.documents import PrintDocument, PlayerRankingPrintDocument
from data.print_documents.player_splitters import ClubPlayerSplitter
from database.sqlite.event.event_store import StoredTournament
from database.sqlite.local_source_database import LocalSourceDatabase
from plugins import PLUGINS_DIR
from plugins.ffe.ffe import FfeLeagueTableColumn, FfePlugin
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.papi_converter import PapiPlayer
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_controller import FRASchoolsController
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra_schools.fra_schools_entity import (
    FraSchoolDatasheetColumn,
    FraSchoolPlayerSplitter,
    FraSchoolTableColumn,
    FRASchoolPlayerFilter,
    FRASchoolsFilterOption,
    FRADepartmentPlayerFilter,
    FRADepartmentsFilterOption,
)
from plugins.fra_schools.fra_schools_event_controller import (
    FraSchoolsAdminEventController,
)
from plugins.fra_schools.fra_schools_ranking_document import (
    FraSchoolsRankingPrintDocument,
)
from plugins.fra_schools.fra_schools_session_handler import FRASchoolsSessionHandler
from plugins.fra_schools.utils import (
    FRASchoolsPlayerPluginData,
    FRASchoolsUtils,
    FRASchoolsEventPluginData,
)
from plugins.hookspec import ExtraAdminColumn, hookimpl
from plugins.manager import Path
from plugins.utils import (
    Plugin,
    PluginData,
    PluginUtils,
)
from web.controllers.admin.player_admin_controller import PlayerAdminWebContext
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
        return PLUGINS_DIR / self.id / 'templates'

    @override
    @property
    def federation(self) -> str | None:
        return 'FRA'

    def used_by_stored_tournament(self, stored_tournament: StoredTournament) -> bool:
        players = stored_tournament.stored_players
        for stored_player in players:
            data = stored_player.plugin_data.get(PLUGIN_NAME, {})
            if data.get('fra_school_id', None) is not None:
                return True
        return False

    def on_enable(self):
        schools_database = FRASchoolsDatabase()
        if not schools_database.exists():
            schools_database.update()

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

    @hookimpl(trylast=True)
    def insert_local_source_databases(self, databases: list[type[LocalSourceDatabase]]):
        schools: type[LocalSourceDatabase] = FRASchoolsDatabase
        ffe: type[LocalSourceDatabase] = FfeDatabase
        PluginUtils.insert_on_equals(databases, schools, ffe, True)

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_event_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, FRASchoolsEventPluginData

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
        event = web_context.get_admin_event()

        school_counts = FRASchoolsUtils.get_event_school_counts(event)
        plugin_data = FRASchoolsUtils.get_event_plugin_data(event)
        sorted_schools = sorted(
            school for school in plugin_data.fra_schools if school.id in school_counts
        )
        sorted_school_ids: list[int] = [school.id for school in sorted_schools]
        if 0 in school_counts:
            sorted_school_ids.insert(0, 0)

        return {
            'fra_schools_utils': FRASchoolsUtils,
            'fra_school_ids': sorted_school_ids,
            'fra_schools_by_id': plugin_data.fra_schools_by_id,
            'fra_school_counts': school_counts,
            'fra_schools_filter': FRASchoolsSessionHandler.get_session_filter_schools(
                web_context.request
            ),
        }

    @hookimpl
    def get_player_form_template_context(
        self, web_context: 'PlayerAdminWebContext'
    ) -> dict[str, Any]:
        return FRASchoolsController.get_fra_school_template_context(web_context)

    @hookimpl
    def insert_player_form_fields_template(
        self, templates_by_section: defaultdict[str, list[str]]
    ):
        templates_by_section['identity'].append('/fra_schools_player_form_fields.html')

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
        filter_schools = FRASchoolsSessionHandler.get_session_filter_schools(
            web_context.request
        )
        schools_ids = template_context['fra_school_ids']
        filters: list[Callable[[Player], bool]] = []
        if len(filter_schools) not in (0, len(schools_ids)):
            filters.append(
                lambda player: (
                    FRASchoolsUtils.get_player_plugin_data(player).fra_school_id or 0
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
            school = FRASchoolsUtils.get_player_school(player)
            return (
                school.full_name_without_code if school else '',
                player.last_name,
                player.first_name,
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
    def insert_print_document(self, print_documents: list[type['PrintDocument']]):
        sps: type[PrintDocument] = FraSchoolsRankingPrintDocument
        pps: type[PrintDocument] = PlayerRankingPrintDocument
        PluginUtils.insert_on_equals(print_documents, sps, pps, True)

    @hookimpl(trylast=True)
    def alter_print_and_screen_player_columns(
        self,
        usage: ColumnUsage,
        player_columns: list['PlayerTableColumn'],
    ):
        # Remove FederationColumn and LeagueColumn
        player_columns[:] = [
            col
            for col in player_columns
            if not isinstance(
                col, (player_table.FederationColumn, FfeLeagueTableColumn)
            )
        ]
        PluginUtils.replace_on_isinstance(
            player_columns,
            FraSchoolTableColumn(usage),
            player_table.ClubColumn,
        )

    @hookimpl
    def insert_print_player_splitter_types(
        self, player_splitter_types: list[type[PlayerSplitter]]
    ):
        lps: type[PlayerSplitter] = FraSchoolPlayerSplitter
        cps: type[PlayerSplitter] = ClubPlayerSplitter
        PluginUtils.insert_on_equals(player_splitter_types, lps, cps, False)

    # ---------------------------------------------------------------------------------
    # Prizes
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_player_filter_types(
        self, player_filter_types: list[type['PlayerFilter']]
    ):
        school: type[PlayerFilter] = FRASchoolPlayerFilter
        club: type[PlayerFilter] = ClubPlayerFilter
        PluginUtils.insert_on_equals(player_filter_types, school, club, False)
        if FRASchoolsDatabase.DEPARTMENTS:
            department: type[PlayerFilter] = FRADepartmentPlayerFilter
            PluginUtils.insert_on_equals(player_filter_types, department, club, False)

    @hookimpl
    def insert_player_filter_option_types(
        self, player_filter_option_types: list[type['PlayerFilterOption']]
    ):
        school: type[PlayerFilterOption] = FRASchoolsFilterOption
        club: type[PlayerFilterOption] = ClubsFilterOption
        PluginUtils.insert_on_equals(player_filter_option_types, school, club, False)
        if FRASchoolsDatabase.DEPARTMENTS:
            department: type[PlayerFilterOption] = FRADepartmentsFilterOption
            PluginUtils.insert_on_equals(
                player_filter_option_types, department, club, False
            )

    # ---------------------------------------------------------------------------------
    # Plugin hooks
    # ---------------------------------------------------------------------------------

    @hookimpl
    def update_papi_player(self, papi_player: PapiPlayer, player: Player):
        school = FRASchoolsUtils.get_player_school(player)
        papi_player.club = school.full_name if school else ''
