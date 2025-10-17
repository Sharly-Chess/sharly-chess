from dataclasses import dataclass
from functools import partial
from typing import Self, Any

from common.i18n import _
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
    id: int | None
    name: str | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            id=stored_value.get('id', None),
            name=stored_value.get('name', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'school_name': self.name,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            id=WebContext.form_data_to_int(data, 'school_id'),
            name=WebContext.form_data_to_str(data, 'school_name'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'school_id': self.id,
                'school_name': self.name,
            }
        )
