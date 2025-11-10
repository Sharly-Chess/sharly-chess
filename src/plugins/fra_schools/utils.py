from dataclasses import dataclass, asdict
from functools import partial, cached_property
from typing import Self, Any, Counter, Collection

from data.event import Player, Event
from plugins.fra_schools import PLUGIN_NAME
from plugins.utils import PluginUtils, PluginData
from web.controllers.base_controller import WebContext

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


@dataclass
class FRASchool(PluginData):
    id: int = 0
    code: str | None = None
    name: str = ''
    department: str | None = None
    city: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any], id_: int = 0) -> Self:
        return cls(
            id=id_,
            code=stored_value.get('code', None),
            name=stored_value.get('name', ''),
            department=stored_value.get('department', None),
            city=stored_value.get('city', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
        id_: int = 0,
    ) -> Self:
        return cls(
            id=id_,
            code=WebContext.form_data_to_str(data, 'fra_school_code'),
            name=WebContext.form_data_to_str(data, 'fra_school_name') or '',
            department=WebContext.form_data_to_str(data, 'fra_school_department'),
            city=WebContext.form_data_to_str(data, 'fra_school_city'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'fra_school_code': self.code,
                'fra_school_name': self.name,
                'fra_school_department': self.department,
                'fra_school_city': self.city,
            }
        )

    @property
    def full_name(self) -> str:
        full_name = self.full_name_without_code
        if self.code:
            full_name = f'{self.code} {full_name}'
        return full_name

    @property
    def full_name_without_code(self) -> str:
        full_name = self.name
        if self.city:
            full_name += f', {self.city}'
        if self.department:
            full_name += f' ({self.department})'
        return full_name

    @cached_property
    def tooltip(self) -> str:
        if not self.code or not self.city:
            return ''
        tooltip = ''
        if self.code:
            tooltip += f'<div class="text-center text-nowrap fw-bold">{self.code}</div>'
        tooltip += f'<div class="text-center text-nowrap">{self.name}</div>'
        if self.city:
            city = self.city
            if self.department:
                city += f' ({self.department})'
            tooltip += f'<div class="text-center text-nowrap fst-italic">{city}</div>'
        return tooltip

    def __lt__(self, other):
        if not isinstance(other, FRASchool):
            return NotImplemented
        return self.full_name_without_code > other.full_name_without_code

    def __eq__(self, other):
        if not isinstance(other, FRASchool):
            return NotImplemented
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


@dataclass
class FRASchoolsEventPluginData(PluginData):
    fra_schools_by_id: dict[int, FRASchool]

    @property
    def fra_schools(self) -> Collection[FRASchool]:
        return self.fra_schools_by_id.values()

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            fra_schools_by_id={
                int(school_id): FRASchool.from_stored_value(
                    school_dict, id_=int(school_id)
                )
                for school_id, school_dict in stored_value.get(
                    'fra_schools_by_id', {}
                ).items()
            }
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'fra_schools_by_id': {
                str(school_id): school.to_stored_value()
                for school_id, school in self.fra_schools_by_id.items()
            }
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object:
            return previous_object
        return cls({})

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class FRASchoolsPlayerPluginData(PluginData):
    fra_school_id: int | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            fra_school_id=stored_value.get('fra_school_id', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'fra_school_id': self.fra_school_id,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            fra_school_id=WebContext.form_data_to_int(data, 'fra_school'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'fra_school': self.fra_school_id,
            }
        )


class FRASchoolsUtils:
    @staticmethod
    def get_event_plugin_data(event: Event) -> FRASchoolsEventPluginData:
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FRASchoolsEventPluginData)
        return plugin_data

    @classmethod
    def get_event_school_counts(cls, event: Event) -> Counter[int]:
        school_counts: Counter[int] = Counter[int]()
        for player in event.players:
            school_counts[
                FRASchoolsUtils.get_player_plugin_data(player).fra_school_id or 0
            ] += 1
        return school_counts

    @staticmethod
    def get_player_plugin_data(player: Player) -> FRASchoolsPlayerPluginData:
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FRASchoolsPlayerPluginData)
        return plugin_data

    @classmethod
    def get_player_school(cls, player: Player) -> FRASchool | None:
        player_school_id = cls.get_player_plugin_data(player).fra_school_id
        if not player_school_id:
            return None
        event_schools_by_id = cls.get_event_plugin_data(
            player.tournament.event
        ).fra_schools_by_id
        return event_schools_by_id.get(player_school_id, None)
