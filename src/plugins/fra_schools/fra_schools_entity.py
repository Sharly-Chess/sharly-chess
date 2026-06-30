from functools import partial, cached_property
from operator import attrgetter
from types import UnionType
from typing import Any, Counter, Callable

from common.exception import OptionError, SharlyChessException
from common.i18n import _
from data.columns.player_datasheet import DatasheetColumn
from data.columns.player_table import TournamentPlayerTableColumn
from data.columns.players_tab import FilterPlayersTabColumn, ColumnFilterValue
from data.criteria.player_filter_options import (
    SelectPlayerFilterOption,
    PlayerFilterOption,
    ExcludeFilterOption,
)
from data.criteria.player_filters import PlayerFilter
from data.event import Event
from data.player import Player, TournamentPlayer
from data.print_documents import PlayerSplitter
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra_schools.utils import (
    FRASchoolsUtils,
    FRASchool,
    FRASchoolsPlayerPluginData,
)
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
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        return getattr(
            FRASchoolsUtils.get_player_school(tournament_player),
            'label',
            '',
        )

    @staticmethod
    def get_empty_key_default() -> str:
        return _('School not specified')


class FraSchoolTableColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('School *** SCHOOL COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return getattr(
            FRASchoolsUtils.get_player_school(tournament_player),
            'label',
            '',
        )

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class FraSchoolCodeDatasheetColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'fra_school_code'

    def get_cell_content(self, player: Player) -> Any:
        school = FRASchoolsUtils.get_player_school(player)
        if not school:
            return None
        return school.code

    @property
    def save_stored_event(self) -> bool:
        return True

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        pass

    def augment_stored_player_with_tournament(
        self, tournament: Tournament | None, stored_player: StoredPlayer, value: str
    ):
        if not value or tournament is None:
            return
        event = tournament.event
        school_code = FRASchoolsUtils.extract_school_code(value)
        if not school_code:
            raise SharlyChessException(
                _('Invalid format (expected: {format}).').format(format='1234567A')
            )
        fra_schools = FRASchoolsUtils.get_event_plugin_data(event).fra_schools
        school_id = next(
            (s.id for s in fra_schools if s.code == school_code),
            None,
        )
        if not school_id:
            with FRASchoolsDatabase() as database:
                school = database.get_school_by_code(school_code)
            if not school:
                raise SharlyChessException(_('UAI code not found in the database.'))
            else:
                school_id = FRASchoolsUtils.add_event_school(event, school, save=False)
        stored_player.plugin_data[PLUGIN_NAME] = FRASchoolsPlayerPluginData(
            school_id
        ).to_stored_value()


class FraSchoolLabelDatasheetColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'fra_school_label'

    def get_cell_content(self, player: Player) -> Any:
        school = FRASchoolsUtils.get_player_school(player)
        if not school:
            return None
        return school.label

    @property
    def export_only(self) -> bool:
        return True

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        pass


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
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        school_ids, exclude = self.get_option_values()
        if exclude:
            return lambda tournament_player: (
                FRASchoolsUtils.get_player_plugin_data(tournament_player).fra_school_id
                not in school_ids
            )
        else:
            return lambda tournament_player: (
                FRASchoolsUtils.get_player_plugin_data(tournament_player).fra_school_id
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
        return sorted(
            FRASchoolsUtils.get_event_plugin_data(tournament.event).fra_schools,
            key=attrgetter('sort_key'),
        )

    def get_tournament_player_counter(
        self, tournament: 'Tournament'
    ) -> Counter[FRASchool]:
        counter: Counter[FRASchool] = Counter[FRASchool]()
        for tournament_player in tournament.tournament_players:
            if school := FRASchoolsUtils.get_player_school(tournament_player):
                counter[school] += 1
        return counter

    def get_key(self, object_: FRASchool) -> str:
        return str(object_.id)

    def get_name(self, object_: FRASchool) -> str:
        return object_.short_name

    def get_tooltip(self, object_: FRASchool) -> str | None:
        return object_.tooltip

    def get_search(self, object_: FRASchool) -> str | None:
        return object_.full_name

    def validate(self):
        self._validate_list_type(int)
        if not self.value:
            raise OptionError(_('At least one school is expected.'), self)


class FraSchoolsPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-school'

    @staticmethod
    def static_name() -> str:
        return _('School *** SCHOOL COLUMN HEADER')

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def align_start(self) -> bool:
        return True

    def get_cell_classes(self, player: Player) -> str:
        return self.shared_classes + ' text-truncate mw-25em'

    @property
    def cell_template(self) -> str | None:
        return '/fra_schools_player_school_cell.html'

    @property
    def is_tournament_column(self) -> bool:
        return True

    def get_filter_key(self, player: Player) -> str:
        school = FRASchoolsUtils.get_player_school(player)
        return str(school.id) if school else ''

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        if not filter_key:
            return None
        return FRASchoolsUtils.get_event_plugin_data(event).fra_schools_by_id[
            int(filter_key)
        ]

    def get_filter_row_content(self, value: Any) -> str:
        return value.short_name if value else '-'

    def get_filter_row_tooltip(self, value: Any) -> str:
        return value.tooltip if value else ''

    def _get_sort_key(self, player: Player) -> tuple:
        school = FRASchoolsUtils.get_player_school(player) or FRASchool()
        return not school.name, school.sort_key

    def get_filter_value_sort_key(self, filter_value: ColumnFilterValue) -> Any:
        return (filter_value.value or FRASchool()).sort_key

    @staticmethod
    def get_player_school(player: Player) -> FRASchool | None:
        return FRASchoolsUtils.get_player_school(player)

    @property
    def is_searchable(self) -> bool:
        return True

    def get_search_key(self, player: Player) -> str:
        school = self.get_player_school(player)
        if not school:
            return ''
        return school.full_name
