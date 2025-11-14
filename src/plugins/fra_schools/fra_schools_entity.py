from functools import partial, cached_property
from types import UnionType
from typing import Any, Counter, Callable

from common.exception import OptionError
from data.columns.player_datasheet import DatasheetColumn
from data.columns.player_table import PlayerTableColumn
from data.criteria.player_filter_options import (
    SelectPlayerFilterOption,
    PlayerFilterOption,
    ExcludeFilterOption,
)
from data.criteria.player_filters import PlayerFilter
from data.player import Player
from data.print_documents import PlayerSplitter
from data.tournament import Tournament
from plugins.fra_schools import _, PLUGIN_NAME
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra_schools.utils import FRASchoolsUtils, FRASchool
from plugins.utils import PluginUtils

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
            FRASchoolsUtils.get_player_school(player), 'full_name_without_code', ''
        )


class FraSchoolTableColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('School *** SCHOOL FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return getattr(
            FRASchoolsUtils.get_player_school(player), 'full_name_without_code', ''
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


class FRASchoolPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-SCHOOL'

    @staticmethod
    def static_name() -> str:
        return _('French school')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            FRASchoolsFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        school_ids, exclude = self.get_option_values()
        if exclude:
            return (
                lambda player: FRASchoolsUtils.get_player_plugin_data(
                    player
                ).fra_school_id
                not in school_ids
            )
        else:
            return (
                lambda player: FRASchoolsUtils.get_player_plugin_data(
                    player
                ).fra_school_id
                in school_ids
            )

    def full_name(self, tournament: 'Tournament') -> str:
        school_ids, exclude = self.get_option_values()
        schools_by_id = FRASchoolsUtils.get_event_plugin_data(
            tournament.event
        ).fra_schools_by_id
        option_str = ', '.join(
            schools_by_id[school_id].name for school_id in school_ids
        )
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'


class FRASchoolsFilterOption(SelectPlayerFilterOption[FRASchool]):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-SCHOOLS'

    @property
    def template_name(self) -> str:
        return '/fra_schools_school_player_filter_option.html'

    @property
    def type(self) -> type | UnionType:
        return list[int]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[FRASchool]:
        return list(FRASchoolsUtils.get_event_plugin_data(tournament.event).fra_schools)

    def get_player_counter(self, tournament: 'Tournament') -> Counter[FRASchool]:
        counter: Counter[FRASchool] = Counter[FRASchool]()
        for player in tournament.players:
            if school := FRASchoolsUtils.get_player_school(player):
                counter[school] += 1
        return counter

    def get_key(self, object_: FRASchool) -> str:
        return str(object_.id)

    def get_name(self, object_: FRASchool) -> str:
        return object_.name

    def get_tooltip(self, object_: FRASchool) -> str | None:
        return object_.tooltip

    def validate(self):
        self._validate_list_type(int)
        if not self.value:
            raise OptionError(_('At least one school is expected.'), self)


class FRADepartmentPlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-DEPARTMENT'

    @staticmethod
    def static_name() -> str:
        return _('Department')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            FRADepartmentsFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        departments, exclude = self.get_option_values()
        if exclude:
            return lambda player: (
                getattr(FRASchoolsUtils.get_player_school(player), 'department', None)
                not in departments
            )
        else:
            return lambda player: (
                getattr(FRASchoolsUtils.get_player_school(player), 'department', None)
                in departments
            )

    def full_name(self, tournament: 'Tournament') -> str:
        departments, exclude = self.get_option_values()
        option_str = ', '.join(departments)
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'


class FRADepartmentsFilterOption(SelectPlayerFilterOption[str]):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-DEPARTMENTS'

    @property
    def template_name(self) -> str:
        return '/fra_schools_department_player_filter_option.html'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[str]:
        return list(FRASchoolsDatabase.DEPARTMENTS or {})

    def get_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        counter = Counter[str]()
        for player in tournament.players:
            school = FRASchoolsUtils.get_player_school(player)
            if school and school.department:
                counter[school.department] += 1
        return counter

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        assert FRASchoolsDatabase.DEPARTMENTS is not None
        return f'{object_} - {FRASchoolsDatabase.DEPARTMENTS[object_]}'

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one department is expected.'), self)
