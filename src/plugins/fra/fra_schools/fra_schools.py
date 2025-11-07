from typing import TYPE_CHECKING, override

from packaging.version import Version

from common.i18n import _
from data.columns.player_datasheet import DatasheetColumn
from data.print_documents import PlayerSplitter
from data.print_documents.player_splitters import ClubPlayerSplitter
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.event.event_store import StoredTournament
from data.columns import player_table, player_datasheet
from plugins import PLUGINS_DIR
from plugins.fra.fra_schools import PLUGIN_NAME
from plugins.fra.fra_schools.fra_schools_controller import FRASchoolsController
from plugins.fra.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra.fra_schools.fra_schools_entity import (
    FraSchoolDatasheetColumn,
    FraSchoolPlayerSplitter,
    FraSchoolTableColumn,
)
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
