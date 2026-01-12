from functools import partial
from typing import Any

from data.columns.player_datasheet import DatasheetColumn
from data.player import Player
from plugins.scf import PLUGIN_NAME
from plugins.scf.utils import SCFUtils
from plugins.utils import PluginUtils

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ScfCodeDatasheetColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'scf_code'

    def get_cell_content(self, player: Player) -> Any:
        return SCFUtils.get_player_plugin_data(player).scf_code or ''
