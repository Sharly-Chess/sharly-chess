from functools import partial
from typing import Any

from common.i18n import _
from data.columns.player_datasheet import DatasheetColumn
from data.player import Player
from data.print_documents import PlayerSplitter
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.utils import FRASchoolsUtils
from plugins.utils import PluginUtils
from web.utils import PlayerColumn

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FraSchoolPlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-school'

    @staticmethod
    def static_name() -> str:
        return _('French school')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return getattr(
            FRASchoolsUtils.get_player_school(player), 'full_name_without_id', ''
        )


class FraSchoolTableColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('School *** SCHOOL FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return getattr(
            FRASchoolsUtils.get_player_school(player), 'full_name_without_id', ''
        )

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class FraSchoolDatasheetColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'school'

    def get_cell_content(self, player: Player) -> Any:
        return getattr(FRASchoolsUtils.get_player_school(player), 'full_name', '')
