from dataclasses import dataclass
from functools import partial
from typing import Self, Any

from data.event import Player
from plugins.fra.fra_schools import PLUGIN_NAME
from plugins.utils import PluginUtils, PluginData
from web.controllers.base_controller import WebContext

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


@dataclass
class StoredSchool:
    school_id: str
    school_name: str
    department: str
    department_name: str
    commune: str
    type: str
    private: int


@dataclass
class FRASchoolsPlayerPluginData(PluginData):
    school_name: str | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            school_name=stored_value.get('school_name', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'school_name': self.school_name,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            school_name=WebContext.form_data_to_str(data, 'fra_school'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'fra_school': self.school_name,
            }
        )


class FRASchoolsUtils:
    @staticmethod
    def get_player_plugin_data(player: Player) -> FRASchoolsPlayerPluginData:
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FRASchoolsPlayerPluginData)
        return plugin_data
