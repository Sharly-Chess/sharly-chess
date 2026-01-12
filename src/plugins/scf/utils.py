from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Self, Any

from data.player import Player
from plugins.scf import PLUGIN_NAME
from plugins.utils import PluginUtils, PluginData
from web.controllers.base_controller import WebContext

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

SCF_MIN_UPLOAD_DELAY = 3
SCF_DEFAULT_UPLOAD_DELAY = 3
SCF_EPOCH = datetime(2000, 1, 1)


class SCFUtils:
    @staticmethod
    def get_player_plugin_data(player: Player) -> 'ScfPlayerPluginData':
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, ScfPlayerPluginData)
        return plugin_data


@dataclass
class ScfPlayerPluginData(PluginData):
    scf_code: int | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            scf_code=stored_value.get('scf_code', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'scf_code': self.scf_code,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(scf_code=WebContext.form_data_to_int(data, 'scf_code'))

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'scf_code': self.scf_code,
            }
        )
