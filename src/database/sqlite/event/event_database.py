import shutil
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime
from functools import cached_property
from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError
from typing import Any, TYPE_CHECKING, override, Self

import yaml
from packaging.version import Version

from common import format_timestamp_date, format_timestamp_time, DEVEL_ENV, EVENTS_DIR
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.board import Board
from data.result import Result as DataResult
from utils.enum import Result as UtilResult
from database.sqlite.event.event_store import (
    StoredClientController,
    StoredTournament,
    StoredEvent,
    StoredTimer,
    StoredTimerHour,
    StoredFamily,
    StoredIllegalMove,
    StoredResult,
    StoredRotator,
    StoredScreenSet,
    StoredScreen,
)
from database.sqlite.event import migrations
from database.sqlite.migration_database import MigrationDatabase
from plugins.manager import plugin_manager

if TYPE_CHECKING:
    from data.loader import EventBackup
    from database.sqlite.migration import DatabaseMigrationManager

logger: Logger = get_logger()


class EventDatabase(MigrationDatabase):
    """The SQLite database class for Papi-web events."""

    def __init__(self, uniq_id: str, write: bool = False):
        self.uniq_id = uniq_id
        super().__init__(self.event_database_path(self.uniq_id), write)

    @classmethod
    def create_instance(cls, file: Path, write: bool = False) -> Self:
        return cls(file.stem, write)

    @cached_property
    def migration_managers(self) -> list['DatabaseMigrationManager']:
        from database.sqlite.migration import DatabaseMigrationManager

        return [DatabaseMigrationManager(self, migrations)] + (
            plugin_manager.hook.get_event_migration_manager(event_database=self)
        )

    @property
    def migration_by_legacy_version(self) -> dict[Version, str]:
        return {
            Version('2.4.0'): 'm001_create_database',
            Version('2.4.2'): 'm002_alter_screens',
            Version('2.4.4'): 'm003_add_input_exit_buttons',
            Version('2.4.5'): 'm004_drop_rotator_show_menu',
            Version('2.4.8'): 'm005_add_hide_background_image',
            Version('2.4.12'): 'm006_add_rules',
            Version('2.4.13'): 'm007_add_last_ffe_rules_upload',
            Version('2.4.16'): 'm008_add_messages',
            Version('2.4.20'): 'm009_add_tournament_check_in_open',
            Version('2.4.21'): 'm010_refactor_chessevent',
            Version('2.4.22'): 'm011_add_tournament_byes',
            Version('2.4.23'): 'm012_add_tournament_tie_breaks',
            Version('2.4.24'): 'm013_replace_tournament_paired_bye_points',
            Version('2.4.25'): 'm014_mark_plugin_columns_as_deprecated',
            Version('2.4.26'): 'm015_add_screen_ranking',
            Version('2.4.27'): 'm016_add_family_ranking',
        }

    @override
    def upgrade(self):
        if DEVEL_ENV and self.is_metadata_table_installed():
            self.create_backup()
        super().upgrade()

    @staticmethod
    def event_database_path(uniq_id: str) -> Path:
        return EVENTS_DIR / f'{uniq_id}.{PapiWebConfig.event_database_ext}'

    @staticmethod
    def _check_populate_dict(
        yml_file: Path,
        dict_path: str,
        supposed_dict: dict,
        mandatory_fields: list[str] | None = None,
        optional_fields: list[str] | None = None,
        field_type: type | None = None,
        empty_allowed: bool = True,
    ):
        """Checks that the given dictionary follows assumptions.
        - `yml_file` is passed for AssertionError reporting only.
        - `dict_path` is passed for AssertionError reporting only.
        - Each field in `mandatory_fields` must appear in the `supposed_dict`
          keys.
        - If `field_type` is provided, all values must be of type `field_type`.
        - If `empty_allowed` is set to False, `supposed_dict` cannot be empty.
        """
        assert (supposed_dict is None and empty_allowed) or isinstance(
            supposed_dict, dict
        ), f'{yml_file.name}: {dict_path}/ is no dictionary'
        fields: list[str] = []
        if mandatory_fields is not None:
            for k in mandatory_fields:
                assert k in supposed_dict, (
                    f'{yml_file.name}: {dict_path}/{k} is not set'
                )
            fields += mandatory_fields
        if optional_fields is not None:
            fields += optional_fields
        if fields:
            for k in supposed_dict:
                assert k in fields, (
                    f'{yml_file.name}: invalid key {dict_path}/{k} (valid_keys: {", ".join(fields)})'
                )
                if field_type is not None:
                    assert isinstance(supposed_dict[k], field_type), (
                        f'{yml_file.name}: {dict_path} should contain only items of type [{field_type}]'
                    )
        if not empty_allowed:
            assert supposed_dict, f'{yml_file.name}: dictionary {dict_path} is empty'

    @staticmethod
    def _check_populate_list(
        yml_file: Path,
        list_path: str,
        supposed_list: list,
        item_type: type | None = None,
        items_number: int | None = None,
        empty_allowed: bool = True,
    ):
        """Checks that the given list follows assumptions.
        - `yml_file` is passed for AssertionError reporting only.
        - If `item_path` is passed for AssertionError reporting only.
        - If `item_type` is provided, all items in `supposed_list` must be of
          this type.
        - If `items_number` is passed, `supposed_list` must contain exactly
          this number of elements.
        - If `allowed_empty is set to False, `supposed_list` must not be empty.
        """
        assert isinstance(supposed_list, list), (
            f'{yml_file.name}: {list_path} is no list'
        )
        if item_type is not None:
            assert all(isinstance(item, item_type) for item in supposed_list), (
                f'{yml_file.name}: {list_path} should contain only items of type [{item_type}]'
            )
        if items_number is not None:
            assert len(supposed_list) == items_number, (
                f'{yml_file.name}: {list_path} should contain exactly {items_number} items'
            )
        if not empty_allowed:
            assert supposed_list, f'{yml_file.name}: list {list_path} is empty'

    def create(self, populate: bool = False):
        """
        Create an event database by running the migrations from scratch.
        The file associated to this database must not exist before calling this method.
        :param populate: if True, the corresponding file in /database/yml is used to populate the database (this way
        example databases are created when no event database is found).
        """

        super().create()
        if populate:
            self._populate()

    def _populate(self):
        try:
            with EventDatabase(self.uniq_id, write=True) as event_database:
                yml_file = PapiWebConfig.database_yml_path / f'{self.uniq_id}.yml'
                event_dict = yaml.safe_load(yml_file.read_text(encoding='utf-8'))
                self._check_populate_dict(
                    yml_file,
                    '',
                    event_dict,
                    mandatory_fields=[
                        'name',
                        'federation',
                    ],
                    optional_fields=[
                        'start',
                        'stop',
                        'path',
                        'hide_background_image',
                        'background_image',
                        'background_color',
                        'public',
                        'update_password',
                        'record_illegal_moves',
                        'rules',
                        'tournaments',
                        'timers',
                        'screens',
                        'families',
                        'rotators',
                        'timer_colors',
                        'timer_delays',
                    ],
                    empty_allowed=False,
                )
                timer_delays: dict[int, int | None] | None = None
                if 'timer_delays' in event_dict:
                    self._check_populate_list(
                        yml_file,
                        '/timer_delays',
                        event_dict['timer_delays'],
                        items_number=3,
                        item_type=int,
                    )
                    timer_delays = {
                        i + 1: event_dict['timer_delays'][i]
                        for i in range(0, len(event_dict['timer_delays']))
                    }
                timer_colors: dict[int, str | None] | None = None
                if 'timer_colors' in event_dict:
                    self._check_populate_list(
                        yml_file,
                        '/timer_colors',
                        event_dict['timer_colors'],
                        items_number=3,
                        item_type=str,
                    )
                    timer_colors = {
                        i + 1: event_dict['timer_colors'][i]
                        for i in range(0, len(event_dict['timer_colors']))
                    }
                today_str: str = format_timestamp_date()
                event_start: float = time.mktime(
                    datetime.strptime(
                        f'{today_str} 00:00', '%Y-%m-%d %H:%M'
                    ).timetuple()
                )
                event_stop: float = time.mktime(
                    datetime.strptime(
                        f'{today_str} 23:59', '%Y-%m-%d %H:%M'
                    ).timetuple()
                )
                if 'start' in event_dict:
                    event_start = time.mktime(
                        datetime.strptime(
                            event_dict['start'], '%Y-%m-%d %H:%M'
                        ).timetuple()
                    )
                if 'stop' in event_dict:
                    event_stop = time.mktime(
                        datetime.strptime(
                            event_dict['stop'], '%Y-%m-%d %H:%M'
                        ).timetuple()
                    )
                event_database.update_stored_event(
                    StoredEvent(
                        uniq_id=self.uniq_id,
                        name=event_dict['name'],
                        federation=event_dict['federation'],
                        start=event_start,
                        stop=event_stop,
                        path=event_dict.get('path', None),
                        hide_background_image=event_dict.get(
                            'hide_background_image',
                            PapiWebConfig.default_hide_background_image,
                        ),
                        background_image=event_dict.get('background_image', None),
                        background_color=event_dict.get('background_color', None),
                        update_password=event_dict.get('update_password', None),
                        record_illegal_moves=event_dict.get(
                            'record_illegal_moves', None
                        ),
                        rules=event_dict.get('rules', None),
                        timer_colors=timer_colors,
                        timer_delays=timer_delays,
                        public=event_dict.get('public', False),
                    )
                )
                timer_ids_by_uniq_id: dict[str, int] = {}
                if 'timers' in event_dict and event_dict['timers'] is not None:
                    self._check_populate_dict(yml_file, '/timers', event_dict['timers'])
                    for timer_uniq_id, timer_dict in event_dict['timers'].items():
                        self._check_populate_dict(
                            yml_file,
                            f'/timers/{timer_uniq_id}',
                            timer_dict,
                            mandatory_fields=[
                                'hours',
                            ],
                            optional_fields=[
                                'delays',
                                'colors',
                            ],
                        )
                        delays: dict[int, int | None] | None = None
                        if 'delays' in timer_dict:
                            self._check_populate_list(
                                yml_file,
                                f'/timers/{timer_uniq_id}/delays',
                                timer_dict['delays'],
                                items_number=3,
                                item_type=int,
                            )
                            delays = {
                                i + 1: timer_dict['delays'][i]
                                for i in range(0, len(timer_dict['delays']))
                            }
                        colors: dict[int, str | None] | None = None
                        if 'colors' in timer_dict:
                            self._check_populate_list(
                                yml_file,
                                f'/timers/{timer_uniq_id}/colors',
                                timer_dict['colors'],
                                items_number=3,
                                item_type=str,
                            )
                            colors = {
                                i + 1: timer_dict['colors'][i]
                                for i in range(0, len(timer_dict['colors']))
                            }
                        stored_timer: StoredTimer = event_database.add_stored_timer(
                            StoredTimer(
                                id=None,
                                uniq_id=timer_uniq_id,
                                colors=colors,
                                delays=delays,
                            )
                        )
                        assert stored_timer.id is not None
                        timer_ids_by_uniq_id[timer_uniq_id] = stored_timer.id
                        self._check_populate_dict(
                            yml_file,
                            f'/timers/{timer_uniq_id}/hours',
                            timer_dict['hours'],
                        )
                        for timer_hour_uniq_id, timer_hour_dict in timer_dict[
                            'hours'
                        ].items():
                            self._check_populate_dict(
                                yml_file,
                                f'/timers/{timer_uniq_id}/hours/{timer_hour_uniq_id}',
                                timer_hour_dict,
                                mandatory_fields=[
                                    'time_str',
                                ],
                                optional_fields=[
                                    'date_str',
                                    'text_before',
                                    'text_after',
                                ],
                            )
                            stored_timer_hour: StoredTimerHour = (
                                event_database.add_stored_timer_hour(stored_timer.id)
                            )
                            stored_timer_hour.uniq_id = timer_hour_uniq_id
                            stored_timer_hour.date_str = timer_hour_dict.get(
                                'date_str', None
                            )
                            stored_timer_hour.time_str = timer_hour_dict['time_str']
                            with suppress(KeyError):
                                stored_timer_hour.text_before = timer_hour_dict.get(
                                    'text_before', None
                                )
                            with suppress(KeyError):
                                stored_timer_hour.text_after = timer_hour_dict.get(
                                    'text_after', None
                                )
                            event_database.update_stored_timer_hour(stored_timer_hour)
                tournament_ids_by_uniq_id: dict[str, int] = {}
                if (
                    'tournaments' in event_dict
                    and event_dict['tournaments'] is not None
                ):
                    self._check_populate_dict(
                        yml_file, '/tournaments', event_dict['tournaments']
                    )
                    for tournament_uniq_id, tournament_dict in event_dict[
                        'tournaments'
                    ].items():
                        self._check_populate_dict(
                            yml_file,
                            f'/tournaments/{tournament_uniq_id}',
                            tournament_dict,
                            mandatory_fields=[
                                'name',
                            ],
                            optional_fields=[
                                'filename',
                                'time_control_initial_time',
                                'time_control_increment',
                                'time_control_handicap_penalty_value',
                                'time_control_handicap_penalty_step',
                                'time_control_handicap_min_time',
                                'time_control_initial_time',
                                'time_control_increment',
                                'time_control_handicap_penalty_value',
                                'time_control_handicap_penalty_step',
                                'time_control_handicap_min_time',
                            ],
                        )
                        stored_tournament: StoredTournament = event_database.add_stored_tournament(
                            StoredTournament(
                                id=None,
                                uniq_id=tournament_uniq_id,
                                path=None,
                                filename=tournament_dict.get('filename', None),
                                name=tournament_dict.get('name', None),
                                time_control_initial_time=tournament_dict.get(
                                    'time_control_initial_time', None
                                ),
                                time_control_increment=tournament_dict.get(
                                    'time_control_increment', None
                                ),
                                time_control_handicap_penalty_value=tournament_dict.get(
                                    'time_control_handicap_penalty_value', None
                                ),
                                time_control_handicap_penalty_step=tournament_dict.get(
                                    'time_control_handicap_penalty_step', None
                                ),
                                time_control_handicap_min_time=tournament_dict.get(
                                    'time_control_handicap_min_time', None
                                ),
                            )
                        )
                        assert stored_tournament.id is not None
                        tournament_ids_by_uniq_id[tournament_uniq_id] = (
                            stored_tournament.id
                        )
                screen_ids_by_uniq_id: dict[str, int] = {}
                if 'screens' in event_dict and event_dict['screens'] is not None:
                    self._check_populate_dict(
                        yml_file, '/screens', event_dict['screens']
                    )
                    for screen_uniq_id, screen_dict in event_dict['screens'].items():
                        self._check_populate_dict(
                            yml_file,
                            f'/screens/{screen_uniq_id}',
                            screen_dict,
                            mandatory_fields=[
                                'type',
                            ],
                            optional_fields=[
                                'public',
                                'timer_uniq_id',
                                'input_exit_button',
                                'players_show_unpaired',
                                'results_limit',
                                'results_tournament_uniq_ids',
                                'ranking_crosstable',
                                'background_image',
                                'background_color',
                                'name',
                                'columns',
                                'font_size',
                                'menu_link',
                                'menu_text',
                                'menu',
                                'sets',
                            ],
                        )
                        assert screen_dict, (
                            f'{yml_file.name}: dictionary screens.{screen_uniq_id} is empty'
                        )
                        timer_uniq_id: str | None = screen_dict.get(
                            'timer_uniq_id', None
                        )
                        timer_id: int | None = (
                            timer_ids_by_uniq_id[timer_uniq_id]
                            if timer_uniq_id
                            else None
                        )
                        type_: str = screen_dict.get('type', None)
                        input_exit_button: bool | None = None
                        players_show_unpaired: bool | None = None
                        results_limit: int | None = None
                        results_max_age: int | None = None
                        results_tournament_ids: list[int] = []
                        ranking_crosstable: bool = False
                        background_image: str | None = None
                        background_color: str | None = None
                        match type_:
                            case 'boards':
                                pass
                            case 'input':
                                input_exit_button = screen_dict.get(
                                    'input_exit_button', False
                                )
                            case 'players':
                                players_show_unpaired = screen_dict.get(
                                    'players_show_unpaired', False
                                )
                            case 'results':
                                results_limit: int = screen_dict.get(
                                    'results_limit', None
                                )
                                results_max_age: int = screen_dict.get(
                                    'results_max_age', None
                                )
                                if 'results_tournament_uniq_ids' in screen_dict:
                                    self._check_populate_list(
                                        yml_file,
                                        f'/screens/{screen_uniq_id}/results_tournament_uniq_ids',
                                        screen_dict['results_tournament_uniq_ids'],
                                    )
                                    results_tournament_ids = [
                                        tournament_ids_by_uniq_id[tournament_uniq_id]
                                        for tournament_uniq_id in screen_dict[
                                            'results_tournament_uniq_ids'
                                        ]
                                    ]
                                else:
                                    results_tournament_ids = []
                            case 'ranking':
                                ranking_crosstable: bool = screen_dict.get(
                                    'ranking_crosstable', False
                                )
                            case 'image':
                                background_image: str = screen_dict.get(
                                    'background_image', None
                                )
                                background_color: str = screen_dict.get(
                                    'background_color', None
                                )
                            case _:
                                raise ValueError
                        menu_link: bool | None = None
                        menu_text: str | None = None
                        menu: str | None = None
                        match type_:
                            case 'boards' | 'input' | 'players' | 'results' | 'ranking':
                                menu_link: bool = screen_dict.get('menu_link', True)
                                menu_text: str = screen_dict.get('menu_text', '')
                                menu: str = screen_dict.get('menu', '')
                            case 'image':
                                background_image: str = screen_dict.get(
                                    'background_image', None
                                )
                                background_color: str = screen_dict.get(
                                    'background_color', None
                                )
                            case _:
                                raise ValueError
                        stored_screen: StoredScreen = event_database.add_stored_screen(
                            StoredScreen(
                                id=None,
                                uniq_id=screen_uniq_id,
                                name=screen_dict.get('name', None),
                                type=type_,
                                public=screen_dict.get('public', True),
                                columns=screen_dict.get('columns', None),
                                font_size=screen_dict.get('font_size', None),
                                menu_link=menu_link,
                                menu_text=menu_text,
                                menu=menu,
                                timer_id=timer_id,
                                input_exit_button=input_exit_button,
                                players_show_unpaired=players_show_unpaired,
                                results_limit=results_limit,
                                results_max_age=results_max_age,
                                results_tournament_ids=results_tournament_ids,
                                ranking_crosstable=ranking_crosstable,
                                background_image=background_image,
                                background_color=background_color,
                            )
                        )
                        assert stored_screen.id is not None
                        screen_ids_by_uniq_id[screen_uniq_id] = stored_screen.id
                        if 'sets' in screen_dict:
                            self._check_populate_list(
                                yml_file,
                                f'/screens/{screen_uniq_id}',
                                screen_dict['sets'],
                            )
                            for screen_set_dict in screen_dict['sets']:
                                self._check_populate_dict(
                                    yml_file,
                                    f'/screens/{screen_uniq_id}/sets',
                                    screen_set_dict,
                                    optional_fields=[
                                        'tournament_uniq_id',
                                        'name',
                                        'fixed_boards_str',
                                        'first',
                                        'last',
                                    ],
                                )
                                tournament_uniq_id: str = screen_set_dict[
                                    'tournament_uniq_id'
                                ]
                                tournament_id: int = tournament_ids_by_uniq_id[
                                    tournament_uniq_id
                                ]
                                stored_screen_set: StoredScreenSet = (
                                    event_database.add_stored_screen_set(
                                        stored_screen.id, tournament_id
                                    )
                                )
                                stored_screen_set.tournament_id = tournament_id
                                stored_screen_set.name = screen_set_dict.get(
                                    'name', None
                                )
                                stored_screen_set.fixed_boards_str = (
                                    screen_set_dict.get('fixed_boards_str', None)
                                )
                                stored_screen_set.first = screen_set_dict.get(
                                    'first', None
                                )
                                stored_screen_set.last = screen_set_dict.get(
                                    'last', None
                                )
                                event_database.update_stored_screen_set(
                                    stored_screen_set
                                )
                family_ids_by_uniq_id: dict[str, int] = {}
                if 'families' in event_dict and event_dict['families'] is not None:
                    self._check_populate_dict(
                        yml_file, '/families', event_dict['families']
                    )
                    for family_uniq_id, family_dict in event_dict['families'].items():
                        self._check_populate_dict(
                            yml_file,
                            f'/families/{family_uniq_id}',
                            family_dict,
                            mandatory_fields=[
                                'type',
                            ],
                            optional_fields=[
                                'public',
                                'tournament_uniq_id',
                                'timer_uniq_id',
                                'input_exit_button',
                                'players_show_unpaired',
                                'ranking_crosstable',
                                'name',
                                'columns',
                                'font_size',
                                'menu_link',
                                'menu_text',
                                'menu',
                                'first',
                                'last',
                                'parts',
                                'number',
                            ],
                        )
                        timer_uniq_id: str | None = family_dict.get(
                            'timer_uniq_id', None
                        )
                        timer_id: int = (
                            timer_ids_by_uniq_id[timer_uniq_id]
                            if timer_uniq_id
                            else None
                        )
                        type_: str = family_dict.get('type', None)
                        tournament_uniq_id: str = family_dict.get('tournament_uniq_id')
                        tournament_id: int = tournament_ids_by_uniq_id[
                            tournament_uniq_id
                        ]
                        input_exit_button: bool | None = None
                        players_show_unpaired: bool | None = None
                        ranking_crosstable: bool = False
                        match type_:
                            case 'boards':
                                pass
                            case 'input':
                                input_exit_button = family_dict.get(
                                    'input_exit_button', False
                                )
                            case 'players':
                                players_show_unpaired = family_dict.get(
                                    'players_show_unpaired', False
                                )
                            case 'ranking':
                                ranking_crosstable = family_dict.get(
                                    'ranking_crosstable', False
                                )
                            case _:
                                raise ValueError(f'type={type_}')
                        match type_:
                            case 'boards' | 'input' | 'players' | 'ranking':
                                menu_link: bool = family_dict.get('menu_link', True)
                                menu_text: str = family_dict.get('menu_text', '')
                                menu: str = family_dict.get('menu', '')
                            case _:
                                raise ValueError(f'type={type_}')
                        stored_family: StoredFamily = event_database.add_stored_family(
                            StoredFamily(
                                id=None,
                                uniq_id=family_uniq_id,
                                name=family_dict.get('name', None),
                                tournament_id=tournament_id,
                                type=type_,
                                public=family_dict.get('public', True),
                                columns=family_dict.get('columns', None),
                                font_size=family_dict.get('font_size', None),
                                menu_link=bool(menu_link),
                                menu_text=menu_text or '',
                                menu=menu or '',
                                timer_id=timer_id,
                                input_exit_button=input_exit_button,
                                players_show_unpaired=players_show_unpaired,
                                ranking_crosstable=ranking_crosstable,
                                ranking_round=None,
                                ranking_min_points=None,
                                ranking_max_points=None,
                                first=family_dict.get('first', None),
                                last=family_dict.get('last', None),
                                parts=family_dict.get('parts', None),
                                number=family_dict.get('number', None),
                            )
                        )
                        assert stored_family.id
                        family_ids_by_uniq_id[family_uniq_id] = stored_family.id
                if 'rotators' in event_dict and event_dict['rotators'] is not None:
                    self._check_populate_dict(
                        yml_file, '/rotators', event_dict['rotators']
                    )
                    for rotator_uniq_id, rotator_dict in event_dict['rotators'].items():
                        self._check_populate_dict(
                            yml_file,
                            f'/rotators/{rotator_uniq_id}',
                            rotator_dict,
                            optional_fields=[
                                'public',
                                'delay',
                                'screen_uniq_ids',
                                'family_uniq_ids',
                            ],
                        )
                        screen_ids: list[int]
                        family_ids: list[int]
                        if 'screen_uniq_ids' in rotator_dict:
                            self._check_populate_list(
                                yml_file,
                                f'/rotator/{rotator_uniq_id}/screen_uniq_ids',
                                rotator_dict['screen_uniq_ids'],
                            )
                            screen_ids = [
                                screen_ids_by_uniq_id[screen_uniq_id]
                                for screen_uniq_id in rotator_dict['screen_uniq_ids']
                            ]
                        else:
                            screen_ids = []
                        if 'family_uniq_ids' in rotator_dict:
                            self._check_populate_list(
                                yml_file,
                                f'/rotator/{rotator_uniq_id}/family_uniq_ids',
                                rotator_dict['family_uniq_ids'],
                            )
                            family_ids = [
                                family_ids_by_uniq_id[family_uniq_id]
                                for family_uniq_id in rotator_dict['family_uniq_ids']
                            ]
                        else:
                            family_ids = []
                        event_database.add_stored_rotator(
                            StoredRotator(
                                id=None,
                                uniq_id=rotator_uniq_id,
                                public=screen_dict.get('public', True),
                                delay=rotator_dict.get('delay', None),
                                screen_ids=screen_ids,
                                family_ids=family_ids,
                            )
                        )
                event_database.commit()
            logger.info('Database [%s] has been populated.', self.file)
        except OperationalError as e:
            logger.warning('Database [%s] creation failed: %s', self.file, e.args)
            self.file.unlink(missing_ok=True)
            raise e

    def delete(self) -> Path:
        """Soft-deletes the event database file by archiving it."""
        file: Path = EventDatabase(self.uniq_id).file
        index: int = 0
        date_str: str = datetime.strftime(datetime.now(), '%Y-%m-%d-%H-%M')
        arch: Path = (
            file.parent / f'{file.stem}_{date_str}.{PapiWebConfig.event_archive_ext}'
        )
        while True:
            try:
                file.rename(arch)
                logger.info('Database has been archived (%s).', arch)
                return arch
            except FileExistsError:
                logger.warning(
                    'Could not rename the database because file [%s] already exists.',
                    arch,
                )
                index += 1
                arch = file.parent / f'{file.stem}_{date_str}-{index}.arch'

    def set_last_update(self):
        """Store the current time as the last time the database was updated."""
        # NOTE(Amaras): We could get in weird territory if time is not
        # monotonic.
        self.execute('UPDATE `info` SET `last_update` = ?', (time.time(),))

    def rename(self, new_uniq_id: str):
        """Changes the event file database to the one associated to the
        provided `new_uniq_id`."""
        self.file.rename(EventDatabase(new_uniq_id).file)
        with EventDatabase(new_uniq_id, write=True) as event_database:
            event_database.set_last_update()
            event_database.commit()

    def clone(self, new_uniq_id: str):
        """Create a copy of the event database file corresponding to an event
        with name `new_uniq_id`."""
        shutil.copy(self.file, EventDatabase(new_uniq_id).file)
        with EventDatabase(new_uniq_id, write=True) as event_database:
            event_database.set_last_update()
            event_database.commit()

    def create_backup(self) -> 'EventBackup':
        """Creates a backup of the event database.
        If a backup already exists for the same version, overwrite it."""
        from data.loader import EventBackup

        backup = EventBackup(self.uniq_id, self.get_version())
        backup.file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.file, backup.file)
        return backup

    # ---------------------------------------------------------------------------------
    # Plugin metadata
    # ---------------------------------------------------------------------------------

    def create_plugin_metadata_table(self):
        self.execute(
            'CREATE TABLE IF NOT EXISTS `plugin_metadata` ('
            '   `name` TEXT NOT NULL,'
            '   `version` TEXT NOT NULL,'
            "   `migration` TEXT NOT NULL DEFAULT 'm000_no_migration',"
            '    PRIMARY KEY(`name`)'
            ')'
        )

    def is_plugin_in_metadata_table(self, plugin_id: str) -> bool:
        self.execute('SELECT 1 FROM `plugin_metadata` WHERE `name` = ?', (plugin_id,))
        return '1' in self.fetchone()

    def insert_plugin_metadata(self, plugin_id: str, version: Version):
        self.execute(
            'INSERT INTO `plugin_metadata` (`name`, `version`) VALUES (?, ?)',
            (plugin_id, str(version)),
        )

    def get_plugin_migration(self, plugin_id: str) -> str:
        self.execute(
            'SELECT `migration` FROM `plugin_metadata` WHERE `name` = ?', (plugin_id,)
        )
        return self.fetchone()['migration']

    def set_plugin_migration(self, plugin_id: str, migration: str):
        self.execute(
            'UPDATE `plugin_metadata` SET `migration` = ? WHERE `name` = ?',
            (migration, plugin_id),
        )

    def get_plugin_version(self, plugin_id: str) -> Version:
        self.execute(
            'SELECT `version` FROM `plugin_metadata` WHERE `name` = ?', (plugin_id,)
        )
        return Version(self.fetchone()['version'])

    def set_plugin_version(self, plugin_id: str, version: Version):
        self.execute(
            'UPDATE `plugin_metadata` SET `version` = ? WHERE `name` = ?',
            (str(version), plugin_id),
        )

    # ---------------------------------------------------------------------------------
    # StoredEvent
    # ---------------------------------------------------------------------------------

    def _row_to_stored_event(self, row: dict[str, Any]) -> StoredEvent:
        """Convert a row to a StoredEvent record."""
        stored_event = StoredEvent(
            uniq_id=self.uniq_id,
            name=row['name'],
            federation=row.get('federation', PapiWebConfig().default_federation),
            start=row['start'],
            stop=row['stop'],
            public=self.load_bool_from_database_field(row['public']),
            path=row['path'],
            location=row['location'],
            hide_background_image=self.load_bool_from_database_field(
                row.get(
                    'hide_background_image', PapiWebConfig.default_hide_background_image
                )
            ),
            background_image=row['background_image'],
            background_color=row['background_color'],
            update_password=row['update_password'],
            record_illegal_moves=row['record_illegal_moves'],
            rules=row['rules'],
            timer_colors=self.set_dict_int_keys(
                self.load_json_from_database_field(row['timer_colors'])
            ),
            timer_delays=self.set_dict_int_keys(
                self.load_json_from_database_field(row['timer_delays'])
            ),
            message_text=row['message_text'],
            message_color=row['message_color'],
            message_background_color=row['message_background_color'],
            last_update=row['last_update'],
        )
        plugin_manager.hook.augment_event_after_db_fetch(
            stored_event=stored_event, row=row
        )
        return stored_event

    def _get_stored_event(self) -> StoredEvent:
        """Gets all the information about the event in the database
        and returns a corresponding StoredEvent record."""
        self.execute(
            'SELECT * FROM `info`',
            (),
        )
        return self._row_to_stored_event(self.fetchone())

    def load_stored_event(self) -> StoredEvent:
        stored_event: StoredEvent = self._get_stored_event()
        stored_event.stored_tournaments = list(self.load_stored_tournaments())
        stored_event.stored_timers = list(self.load_stored_timers())
        stored_event.stored_families = list(self.load_stored_families())
        stored_event.stored_screens = list(self.load_stored_screens())
        stored_event.stored_rotators = list(self.load_stored_rotators())
        stored_event.stored_client_controllers = list(
            self.load_stored_client_controllers()
        )
        return stored_event

    def update_stored_event(self, stored_event: StoredEvent) -> StoredEvent:
        """Updates the event database with the information in the provided
        `stored_event`."""

        per_plugin_event_data = plugin_manager.hook.event_data_for_db_write(
            stored_event=stored_event
        )
        plugin_data = {
            key: value for data in per_plugin_event_data for key, value in data.items()
        }

        fields: list[str] = [
            'name',
            'start',
            'stop',
            'public',
            'federation',
            'path',
            'location',
            'hide_background_image',
            'background_image',
            'background_color',
            'update_password',
            'record_illegal_moves',
            'rules',
            'timer_colors',
            'timer_delays',
            'message_text',
            'message_color',
            'message_background_color',
            'last_update',
        ] + [field for field in plugin_data.keys()]

        params: list = [
            stored_event.name,
            stored_event.start,
            stored_event.stop,
            stored_event.public,
            stored_event.federation,
            stored_event.path,
            stored_event.location,
            stored_event.hide_background_image,
            stored_event.background_image,
            stored_event.background_color,
            stored_event.update_password,
            stored_event.record_illegal_moves,
            stored_event.rules,
            self.dump_to_json_database_timer_colors(stored_event.timer_colors),
            self.dump_to_json_database_timer_delays(stored_event.timer_delays),
            stored_event.message_text,
            stored_event.message_color,
            stored_event.message_background_color,
            time.time(),
        ] + [value for value in plugin_data.values()]

        field_sets = (f'`{f}` = ?' for f in fields)
        self.execute(f'UPDATE `info` SET {", ".join(field_sets)}', tuple(params))
        return self._get_stored_event()

    # ---------------------------------------------------------------------------------
    # StoredTimerHour
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _row_to_stored_timer_hour(row: dict[str, Any]) -> StoredTimerHour:
        return StoredTimerHour(
            id=row['id'],
            uniq_id=row['uniq_id'],
            timer_id=row['timer_id'],
            order=row['order'],
            date_str=row['date_str'],
            time_str=row['time_str'],
            text_before=row['text_before'],
            text_after=row['text_after'],
        )

    def get_stored_timer_hour(self, timer_hour_id: int) -> StoredTimerHour | None:
        self.execute(
            'SELECT * FROM `timer_hour` WHERE `id` = ?',
            (timer_hour_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_timer_hour(row)
        return None

    def get_stored_timer_next_hour_order(self, timer_id: int) -> int:
        self.execute(
            'SELECT MAX(`order`) AS order_max FROM `timer_hour` WHERE `timer_id` = ?',
            (timer_id,),
        )
        row: dict[str, Any] = self.fetchone()
        return (row['order_max'] if row['order_max'] else 0) + 1

    def get_stored_timer_next_round(self, timer_id: int) -> int:
        self.execute(
            'SELECT `uniq_id` FROM `timer_hour` WHERE `timer_id` = ?',
            (timer_id,),
        )
        highest_round: int = 0
        for row in self.fetchall():
            with suppress(ValueError):
                highest_round = max(highest_round, int(row['uniq_id']))
        return highest_round + 1

    def load_stored_timer_hours(self, timer_id: int) -> Iterator[StoredTimerHour]:
        self.execute(
            'SELECT * FROM `timer_hour` WHERE `timer_id` = ? ORDER BY `order`',
            (timer_id,),
        )
        yield from map(self._row_to_stored_timer_hour, self.fetchall())

    def _write_stored_timer_hour(
        self,
        stored_timer_hour: StoredTimerHour,
    ) -> StoredTimerHour:
        fields: list[str] = [
            'timer_id',
            'uniq_id',
            'order',
            'date_str',
            'time_str',
            'text_before',
            'text_after',
        ]
        params: list = [
            stored_timer_hour.timer_id,
            stored_timer_hour.uniq_id,
            stored_timer_hour.order,
            stored_timer_hour.date_str,
            stored_timer_hour.time_str,
            stored_timer_hour.text_before,
            stored_timer_hour.text_after,
        ]
        if stored_timer_hour.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `timer_hour`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            timer_hour_id: int | None = self._last_inserted_id()
            if timer_hour_id is None:
                raise RuntimeError('Timer hour insertion failed')
            fetched_stored_timer_hour = self.get_stored_timer_hour(timer_hour_id)
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_timer_hour.id]
            self.execute(
                f'UPDATE `timer_hour` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_timer_hour = self.get_stored_timer_hour(stored_timer_hour.id)
        if fetched_stored_timer_hour is None:
            raise RuntimeError('Timer hour write failed')
        self.set_last_update()
        return fetched_stored_timer_hour

    def reorder_stored_timer_hours(
        self,
        timer_hour_ids: list[int],
    ):
        order: int = 1
        for timer_hour_id in timer_hour_ids:
            self.execute(
                'UPDATE `timer_hour` SET `order` = ? WHERE `id` = ?',
                (
                    order,
                    timer_hour_id,
                ),
            )
            order += 1
        self.set_last_update()

    def update_stored_timer_hour(
        self,
        stored_timer_hour: StoredTimerHour,
    ) -> StoredTimerHour:
        assert stored_timer_hour.id is not None
        return self._write_stored_timer_hour(stored_timer_hour)

    def add_stored_timer_hour(
        self,
        timer_id: int,
        set_datetime: bool = False,
    ) -> StoredTimerHour:
        stored_timer_hour: StoredTimerHour = StoredTimerHour(
            id=None,
            timer_id=timer_id,
            uniq_id=str(self.get_stored_timer_next_round(timer_id)),
            order=self.get_stored_timer_next_hour_order(timer_id),
        )
        if set_datetime:
            stored_timer_hour.date_str = format_timestamp_date()
            stored_timer_hour.time_str = format_timestamp_time(time.time())
        return self._write_stored_timer_hour(stored_timer_hour)

    def clone_stored_timer_hour(self, timer_hour_id: int, timer_id: int | None = None):
        stored_timer_hour = self.get_stored_timer_hour(timer_hour_id)
        if stored_timer_hour is None:
            raise RuntimeError('Unable to fetch timer hour to clone')
        stored_timer_hour.id = None
        if timer_id is None:
            round_: int = 0
            try:
                round_ = int(stored_timer_hour.uniq_id)
            except ValueError:
                pass
            stored_timer_hour.order = self.get_stored_timer_next_hour_order(
                stored_timer_hour.timer_id
            )
            if round_:
                stored_timer_hour.uniq_id = str(
                    self.get_stored_timer_next_round(stored_timer_hour.timer_id)
                )
            else:
                self.execute(
                    'SELECT uniq_id FROM `timer_hour` WHERE `timer_id` = ?',
                    (stored_timer_hour.timer_id,),
                )
                uniq_ids: list[str] = [row['uniq_id'] for row in self.fetchall()]
                uniq_id: str = f'{stored_timer_hour.uniq_id}-clone'
                clone_index: int = 1
                stored_timer_hour.uniq_id = uniq_id
                while stored_timer_hour.uniq_id in uniq_ids:
                    clone_index += 1
                    stored_timer_hour.uniq_id = f'{uniq_id}{clone_index}'
        else:
            stored_timer_hour.timer_id = timer_id
        return self._write_stored_timer_hour(stored_timer_hour)

    def delete_stored_timer_hour(self, timer_hour_id: int, timer_id: int):
        self.execute('DELETE FROM `timer_hour` WHERE `id` = ?;', (timer_hour_id,))
        order: int = 1
        for stored_timer_hour in self.load_stored_timer_hours(timer_id):
            self.execute(
                'UPDATE `timer_hour` SET `order` = ? WHERE `id` = ?',
                (
                    order,
                    stored_timer_hour.id,
                ),
            )
            order += 1
        self.set_last_update()

    def _delete_stored_timer_hours(self, timer_id: int):
        self.execute('DELETE FROM `timer_hour` WHERE `timer_id` = ?;', (timer_id,))

    # ---------------------------------------------------------------------------------
    # StoredTimer
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_timer(cls, row: dict[str, Any]) -> StoredTimer:
        return StoredTimer(
            id=row['id'],
            uniq_id=row['uniq_id'],
            colors=cls.set_dict_int_keys(
                cls.load_json_from_database_field(row['colors'])
            ),
            delays=cls.set_dict_int_keys(
                cls.load_json_from_database_field(row['delays'])
            ),
        )

    def get_stored_timer(self, timer_id: int) -> StoredTimer:
        self.execute(
            'SELECT * FROM `timer` WHERE `id` = ?',
            (timer_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_timer(row)
        raise RuntimeError('Unable to fetch timer to load')

    def get_stored_timer_ids(self) -> Iterator[int]:
        self.execute(
            'SELECT `id` FROM `timer` ORDER BY `uniq_id`',
            (),
        )
        for row in self.fetchall():
            yield row['id']

    def load_stored_timers(self) -> Iterator[StoredTimer]:
        for stored_timer_id in self.get_stored_timer_ids():
            stored_timer: StoredTimer = self.get_stored_timer(stored_timer_id)
            assert stored_timer.id is not None
            stored_timer.stored_timer_hours = list(
                self.load_stored_timer_hours(stored_timer.id)
            )
            yield stored_timer

    def _write_stored_timer(
        self,
        stored_timer: StoredTimer,
    ) -> StoredTimer:
        fields: list[str] = [
            'uniq_id',
            'colors',
            'delays',
        ]
        params: list = [
            stored_timer.uniq_id,
            self.dump_to_json_database_timer_colors(stored_timer.colors),
            self.dump_to_json_database_timer_delays(stored_timer.delays),
        ]
        if stored_timer.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `timer`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            timer_id: int | None = self._last_inserted_id()
            if timer_id is None:
                raise RuntimeError('Timer insertion failed')
            fetched_stored_timer = self.get_stored_timer(timer_id)
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_timer.id]
            self.execute(
                f'UPDATE `timer` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_timer = self.get_stored_timer(stored_timer.id)
        if fetched_stored_timer is None:
            raise RuntimeError('Timer write failed')
        self.set_last_update()
        return fetched_stored_timer

    def add_stored_timer(
        self,
        stored_timer: StoredTimer,
    ) -> StoredTimer:
        assert stored_timer.id is None, f'stored_timer.id={stored_timer.id}'
        return self._write_stored_timer(stored_timer)

    def update_stored_timer(
        self,
        stored_timer: StoredTimer,
    ) -> StoredTimer:
        assert stored_timer.id is not None
        return self._write_stored_timer(stored_timer)

    def delete_stored_timer(self, timer_id: int):
        self.execute(
            'UPDATE `family` SET `timer_id` = NULL WHERE `timer_id` = ?;', (timer_id,)
        )
        self.execute(
            'UPDATE `screen` SET `timer_id` = NULL WHERE `timer_id` = ?;', (timer_id,)
        )
        self._delete_stored_timer_hours(timer_id)
        # references are not deleted as they should be!
        self.execute('DELETE FROM `timer` WHERE id = ?;', (timer_id,))
        self.set_last_update()

    # ---------------------------------------------------------------------------------
    # StoredTournament
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_tournament(cls, row: dict[str, Any]) -> StoredTournament:
        stored_tournament = StoredTournament(
            id=row['id'],
            uniq_id=row['uniq_id'],
            name=row['name'],
            path=row['path'],
            filename=row['filename'],
            time_control_initial_time=row['time_control_initial_time'],
            time_control_increment=row['time_control_increment'],
            time_control_handicap_penalty_step=row[
                'time_control_handicap_penalty_step'
            ],
            time_control_handicap_penalty_value=row[
                'time_control_handicap_penalty_value'
            ],
            time_control_handicap_min_time=row['time_control_handicap_min_time'],
            record_illegal_moves=row['record_illegal_moves'],
            rules=row['rules'],
            first_board_number=row['first_board_number'],
            paired_bye_result=row['paired_bye_result'],
            max_byes=row['max_byes'],
            last_rounds_no_byes=row['last_rounds_no_byes'],
            check_in_open=cls.load_bool_from_database_field(row['check_in_open']),
            rounds=row['rounds'],
            rating=row['rating'],
            last_update=row['last_update'],
            last_result_update=row['last_result_update'],
            last_illegal_move_update=row['last_illegal_move_update'],
            last_check_in_update=row['last_check_in_update'],
            tie_breaks=cls.load_json_from_database_field(row['tie_breaks']),
            start=row['start'],
            stop=row['stop'],
            location=row['location'],
        )
        plugin_manager.hook.augment_tournament_after_db_fetch(
            stored_tournament=stored_tournament, row=row
        )
        return stored_tournament

    def get_stored_tournament(self, tournament_id: int) -> StoredTournament | None:
        self.execute(
            'SELECT * FROM `tournament` WHERE `id` = ?',
            (tournament_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_tournament(row)
        return None

    def load_stored_tournaments(self) -> Iterator[StoredTournament]:
        self.execute(
            'SELECT * FROM `tournament` ORDER BY `uniq_id`',
            (),
        )
        yield from map(self._row_to_stored_tournament, self.fetchall())

    def _write_stored_tournament(
        self,
        stored_tournament: StoredTournament,
    ) -> StoredTournament:
        per_plugin_tournament_data = plugin_manager.hook.tournament_data_for_db_write(
            stored_tournament=stored_tournament
        )
        plugin_data = {
            key: value
            for data in per_plugin_tournament_data
            for key, value in data.items()
        }

        # check_in_open is not updated here but in set_tournament_check_in()
        fields: list[str] = [
            'uniq_id',
            'name',
            'path',
            'filename',
            'time_control_initial_time',
            'time_control_increment',
            'time_control_handicap_penalty_step',
            'time_control_handicap_penalty_value',
            'time_control_handicap_min_time',
            'record_illegal_moves',
            'rules',
            'first_board_number',
            'paired_bye_result',
            'max_byes',
            'tie_breaks',
            'rounds',
            'rating',
            'location',
            'start',
            'stop',
            'last_rounds_no_byes',
            'last_update',
            'last_result_update',
            'last_illegal_move_update',
            'last_check_in_update',
        ] + [field for field in plugin_data.keys()]

        params: list = [
            stored_tournament.uniq_id,
            stored_tournament.name,
            stored_tournament.path,
            stored_tournament.filename,
            stored_tournament.time_control_initial_time,
            stored_tournament.time_control_increment,
            stored_tournament.time_control_handicap_penalty_step,
            stored_tournament.time_control_handicap_penalty_value,
            stored_tournament.time_control_handicap_min_time,
            stored_tournament.record_illegal_moves,
            stored_tournament.rules,
            stored_tournament.first_board_number,
            stored_tournament.paired_bye_result,
            stored_tournament.max_byes,
            self.dump_to_json_database_field(stored_tournament.tie_breaks),
            stored_tournament.rounds,
            stored_tournament.rating,
            stored_tournament.location,
            stored_tournament.start,
            stored_tournament.stop,
            stored_tournament.last_rounds_no_byes,
            time.time(),
            stored_tournament.last_result_update,
            stored_tournament.last_illegal_move_update,
            stored_tournament.last_check_in_update,
        ] + [value for value in plugin_data.values()]

        if stored_tournament.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `tournament`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            tournament_id: int | None = self._last_inserted_id()
            if tournament_id is None:
                raise RuntimeError('Tournament insertion failed')
            fetched_stored_tournament = self.get_stored_tournament(tournament_id)
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_tournament.id]
            self.execute(
                f'UPDATE `tournament` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_tournament = self.get_stored_tournament(stored_tournament.id)
        if fetched_stored_tournament is None:
            raise RuntimeError('Tournament write failed')
        self.set_last_update()
        return fetched_stored_tournament

    def add_stored_tournament(
        self,
        stored_tournament: StoredTournament,
    ) -> StoredTournament:
        assert stored_tournament.id is None, (
            f'stored_tournament.id={stored_tournament.id}'
        )
        return self._write_stored_tournament(stored_tournament)

    def update_stored_tournament(
        self,
        stored_tournament: StoredTournament,
    ) -> StoredTournament:
        assert stored_tournament.id is not None
        return self._write_stored_tournament(stored_tournament)

    def delete_stored_tournament(self, tournament_id: int):
        self._delete_tournament_stored_screens(tournament_id)
        self._delete_tournament_stored_families(tournament_id)
        self._delete_tournament_stored_illegal_moves(tournament_id)
        self._delete_tournament_stored_results(tournament_id)
        # references are not deleted on cascade as they should be!
        self.execute('DELETE FROM `tournament` WHERE `id` = ?;', (tournament_id,))
        self.set_last_update()

    def _set_tournament_last_illegal_move_update(self, tournament_id: int):
        self.execute(
            'UPDATE `tournament` SET `last_illegal_move_update` = ? WHERE `id` = ?',
            (
                time.time(),
                tournament_id,
            ),
        )

    def set_tournament_last_check_in_update(self, tournament_id: int):
        self.execute(
            'UPDATE `tournament` SET `last_check_in_update` = ? WHERE `id` = ?',
            (
                time.time(),
                tournament_id,
            ),
        )

    def set_tournament_last_result_update(self, tournament_id: int):
        self.execute(
            'UPDATE `tournament` SET `last_result_update` = ? WHERE `id` = ?',
            (
                time.time(),
                tournament_id,
            ),
        )

    def set_tournament_check_in(self, tournament_id: int, o: bool):
        """Opens (o is True) or closes (o is False) the check_in for the tournament."""
        self.execute(
            'UPDATE `tournament` SET `check_in_open` = ?, `last_check_in_update` = ? WHERE `id` = ?',
            (
                1 if o else 0,
                time.time(),
                tournament_id,
            ),
        )

    # ---------------------------------------------------------------------------------
    # Illegal moves
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _row_to_stored_illegal_move(row: dict[str, Any]) -> StoredIllegalMove:
        return StoredIllegalMove(
            id=row['id'],
            tournament_id=row['tournament_id'],
            round=row['round'],
            player_id=row['player_id'],
            date=row['date'],
        )

    def _get_stored_illegal_move(
        self,
        illegal_move_id: int,
    ) -> StoredIllegalMove | None:
        self.execute(
            'SELECT * FROM `illegal_move` WHERE `id` = ?',
            (illegal_move_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_illegal_move(row)
        return None

    def get_stored_illegal_moves(self, tournament_id: int, round_: int) -> Counter[int]:
        self.execute(
            'SELECT `illegal_move`.* '
            'FROM `illegal_move` '
            'JOIN `tournament` ON `illegal_move`.`tournament_id` = `tournament`.`id`'
            'WHERE `tournament`.`id` = ? AND `round` = ?',
            (
                tournament_id,
                round_,
            ),
        )
        illegal_moves: Counter[int] = Counter[int]()
        for row in self.fetchall():
            illegal_moves[int(row['player_id'])] += 1
        return illegal_moves

    def add_stored_illegal_move(
        self, tournament_id: int, round_: int, player_id: int
    ) -> StoredIllegalMove:
        self._set_tournament_last_illegal_move_update(tournament_id)
        fields: list[str] = [
            'tournament_id',
            'round',
            'player_id',
            'date',
        ]
        params: list = [tournament_id, round_, player_id, time.time()]
        protected_fields = [f'`{f}`' for f in fields]
        self.execute(
            f'INSERT INTO `illegal_move`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
            tuple(params),
        )
        illegal_move_id: int | None = self._last_inserted_id()
        if illegal_move_id is None:
            raise RuntimeError('Illegal move insertion failed')
        fetched_stored_illegal_move = self._get_stored_illegal_move(illegal_move_id)
        if fetched_stored_illegal_move is None:
            raise RuntimeError('Illegal move write failed')
        return fetched_stored_illegal_move

    def delete_stored_illegal_move(
        self, tournament_id: int, round_: int, player_id: int
    ) -> bool:
        self._set_tournament_last_illegal_move_update(tournament_id)
        self.execute(
            'SELECT `id` FROM `illegal_move` WHERE `tournament_id` = ? AND `round` = ? AND `player_id` = ? LIMIT 1',
            (
                tournament_id,
                round_,
                player_id,
            ),
        )
        row: dict[str, Any] = self.fetchone()
        if not row:
            return False
        self.execute(
            'DELETE FROM `illegal_move` WHERE `id` = ?',
            (row['id'],),
        )
        return True

    def _delete_tournament_stored_illegal_moves(
        self, tournament_id: int, round_: int = 0
    ):
        self._set_tournament_last_illegal_move_update(tournament_id)
        if round_:
            self.execute(
                'DELETE FROM `illegal_move` WHERE `tournament_id` = ? AND `round` = ?',
                (
                    tournament_id,
                    round_,
                ),
            )
        else:
            self.execute(
                'DELETE FROM `illegal_move` WHERE `tournament_id` = ?',
                (tournament_id,),
            )

    # ---------------------------------------------------------------------------------
    # results
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _row_to_stored_result(row: dict[str, Any]) -> StoredResult:
        return StoredResult(
            id=row['id'],
            tournament_id=row['tournament_id'],
            board_id=row['board_id'],
            result=row['result'],
            date=row['date'],
        )

    def _get_stored_result(
        self,
        result_id: int,
    ) -> StoredResult | None:
        self.execute(
            'SELECT * FROM `result` WHERE `id` = ?',
            (result_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_result(row)
        return None

    def add_stored_result(
        self, tournament_id: int, round_: int, board: Board, result: UtilResult
    ):
        assert board.id is not None
        assert board.white_player is not None
        assert board.black_player is not None
        self.set_tournament_last_result_update(tournament_id)
        self.execute(
            'INSERT INTO `result`('
            '    `tournament_id`, `round`, `board_id`, '
            '    `white_player_id`, `black_player_id`, '
            '    `value`, `date`'
            ') VALUES(?, ?, ?, ?, ?, ?, ?)',
            (
                tournament_id,
                round_,
                board.id,
                board.white_player.id,
                board.black_player.id,
                result,
                time.time(),
            ),
        )

    def delete_stored_result(self, tournament_id: int, round_: int, board_id: int):
        self.set_tournament_last_result_update(tournament_id)
        self.execute(
            'DELETE FROM `result` WHERE `tournament_id` = ? AND `round` = ? AND `board_id` = ?',
            (tournament_id, round_, board_id),
        )

    def _delete_tournament_stored_results(self, tournament_id: int):
        self.execute(
            'DELETE FROM `result` WHERE `tournament_id` = ?',
            (tournament_id,),
        )

    def get_stored_results(
        self, limit: int, tournament_ids: list[int], max_age: int
    ) -> list[DataResult]:
        params: list = [time.time() - max_age * 60]
        if not tournament_ids:
            query: str = (
                'SELECT     * FROM `result` WHERE `date` > ?ORDER BY `date` DESC'
            )
        else:
            query: str = (
                'SELECT '
                '    * '
                'FROM `result` '
                f'WHERE `date` > ? AND ({" OR ".join(["`tournament_id` = ?"] * len(tournament_ids))}) '
                'ORDER BY `date` DESC'
            )
            params += tournament_ids
        if limit:
            query += ' LIMIT ?'
            params += [
                limit,
            ]
        self.execute(query, tuple(params))
        results: list[DataResult] = []
        for row in self.fetchall():
            try:
                value: UtilResult = UtilResult.from_papi_value(int(row['value']))
            except ValueError:
                logger.warning('Invalid result [%s] found in database.', row['value'])
                continue
            results.append(
                DataResult(
                    row['date'],
                    row['tournament_id'],
                    row['round'],
                    row['board_id'],
                    row['white_player_id'],
                    row['black_player_id'],
                    value,
                )
            )
        return results

    # ---------------------------------------------------------------------------------
    # StoredFamily
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_family(cls, row: dict[str, Any]) -> StoredFamily:
        return StoredFamily(
            id=row['id'],
            uniq_id=row['uniq_id'],
            name=row['name'],
            type=row['type'],
            public=cls.load_bool_from_database_field(row['public']),
            tournament_id=row['tournament_id'],
            input_exit_button=cls.load_bool_or_none_from_database_field(
                row['input_exit_button']
            ),
            players_show_unpaired=cls.load_bool_or_none_from_database_field(
                row['players_show_unpaired']
            ),
            ranking_crosstable=cls.load_bool_from_database_field(
                row['ranking_crosstable']
            ),
            ranking_round=row['ranking_round'],
            ranking_min_points=row['ranking_min_points'],
            ranking_max_points=row['ranking_max_points'],
            columns=row['columns'],
            font_size=row['font_size'],
            menu_link=cls.load_bool_from_database_field(row['menu_link']),
            menu_text=row['menu_text'],
            menu=row['menu'],
            timer_id=row['timer_id'],
            first=row['first'],
            last=row['last'],
            parts=row['parts'],
            number=row['number'],
            message_default=cls.load_bool_from_database_field(row['message_default']),
            message_text=row['message_text'],
            last_update=row['last_update'],
        )

    def get_stored_family(self, family_id: int) -> StoredFamily | None:
        self.execute(
            'SELECT * FROM `family` WHERE `id` = ?',
            (family_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_family(row)
        return None

    def load_stored_families(self) -> Iterator[StoredFamily]:
        self.execute(
            'SELECT * FROM `family` ORDER BY `uniq_id`',
            (),
        )
        yield from map(self._row_to_stored_family, self.fetchall())

    def _write_stored_family(
        self,
        stored_family: StoredFamily,
    ) -> StoredFamily:
        fields: list[str] = [
            'uniq_id',
            'name',
            'type',
            'public',
            'tournament_id',
            'columns',
            'font_size',
            'menu_link',
            'menu_text',
            'menu',
            'timer_id',
            'input_exit_button',
            'players_show_unpaired',
            'ranking_crosstable',
            'ranking_round',
            'ranking_min_points',
            'ranking_max_points',
            'first',
            'last',
            'parts',
            'number',
            'message_default',
            'message_text',
            'last_update',
        ]
        params: list = [
            stored_family.uniq_id,
            stored_family.name,
            stored_family.type,
            stored_family.public,
            stored_family.tournament_id,
            stored_family.columns,
            stored_family.font_size,
            stored_family.menu_link,
            stored_family.menu_text,
            stored_family.menu,
            stored_family.timer_id,
            stored_family.input_exit_button,
            stored_family.players_show_unpaired,
            stored_family.ranking_crosstable,
            stored_family.ranking_round,
            stored_family.ranking_min_points,
            stored_family.ranking_max_points,
            stored_family.first,
            stored_family.last,
            stored_family.parts,
            stored_family.number,
            stored_family.message_default,
            stored_family.message_text,
            time.time(),
        ]
        if stored_family.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `family`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            family_id: int | None = self._last_inserted_id()
            if family_id is None:
                raise RuntimeError('Family insertion failed')
            fetched_stored_family = self.get_stored_family(family_id)
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_family.id]
            self.execute(
                f'UPDATE `family` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_family = self.get_stored_family(stored_family.id)
        if fetched_stored_family is None:
            raise RuntimeError('Family write failed')
        self.set_last_update()
        return fetched_stored_family

    def add_stored_family(
        self,
        stored_family: StoredFamily,
    ) -> StoredFamily:
        assert stored_family.id is None, f'stored_family.id={stored_family.id}'
        return self._write_stored_family(stored_family)

    def update_stored_family(
        self,
        stored_family: StoredFamily,
    ) -> StoredFamily:
        assert stored_family.id is not None
        return self._write_stored_family(stored_family)

    def delete_stored_family(self, family_id: int):
        self.execute('DELETE FROM `family` WHERE `id` = ?;', (family_id,))
        self.set_last_update()

    def _delete_tournament_stored_families(self, tournament_id: int):
        self.execute(
            'DELETE FROM `family` WHERE `tournament_id` = ?;', (tournament_id,)
        )

    # ---------------------------------------------------------------------------------
    # StoredScreen
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_screen(cls, row: dict[str, Any]) -> StoredScreen:
        return StoredScreen(
            id=row['id'],
            uniq_id=row['uniq_id'],
            name=row['name'],
            type=row['type'],
            public=cls.load_bool_from_database_field(row['public']),
            columns=row['columns'],
            font_size=row['font_size'],
            menu_link=cls.load_bool_or_none_from_database_field(row['menu_link']),
            menu_text=row['menu_text'],
            menu=row['menu'],
            timer_id=row['timer_id'],
            input_exit_button=cls.load_bool_or_none_from_database_field(
                row['input_exit_button']
            ),
            players_show_unpaired=cls.load_bool_or_none_from_database_field(
                row['players_show_unpaired']
            ),
            results_limit=row['results_limit'],
            results_max_age=row['results_max_age'],
            results_tournament_ids=cls.load_json_from_database_field(
                row['results_tournament_ids']
            ),
            ranking_crosstable=cls.load_bool_from_database_field(
                row['ranking_crosstable']
            ),
            ranking_round=row['ranking_round'],
            ranking_min_points=row['ranking_min_points'],
            ranking_max_points=row['ranking_max_points'],
            background_image=row['background_image'],
            background_color=row['background_color'],
            message_default=cls.load_bool_from_database_field(row['message_default']),
            message_text=row['message_text'],
            last_update=row['last_update'],
        )

    def get_stored_screen(self, screen_id: int) -> StoredScreen | None:
        self.execute(
            'SELECT * FROM `screen` WHERE `id` = ?',
            (screen_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_screen(row)
        return None

    def load_stored_screens(self) -> Iterator[StoredScreen]:
        self.execute(
            'SELECT * FROM `screen` ORDER BY `uniq_id`',
            (),
        )
        for row in self.fetchall():
            stored_screen: StoredScreen = self._row_to_stored_screen(row)
            assert stored_screen.id is not None
            stored_screen.stored_screen_sets = list(
                self.load_stored_screen_sets(stored_screen.id)
            )
            yield stored_screen

    def _set_stored_screen_last_update(self, screen_id: int):
        self.execute(
            'UPDATE `screen` SET `last_update` = ? WHERE `id` = ?',
            (
                time.time(),
                screen_id,
            ),
        )

    def _write_stored_screen(
        self,
        stored_screen: StoredScreen,
    ) -> StoredScreen:
        fields: list[str] = [
            'uniq_id',
            'name',
            'type',
            'public',
            'input_exit_button',
            'players_show_unpaired',
            'columns',
            'font_size',
            'menu_link',
            'menu_text',
            'menu',
            'timer_id',
            'results_limit',
            'results_max_age',
            'results_tournament_ids',
            'ranking_crosstable',
            'ranking_round',
            'ranking_min_points',
            'ranking_max_points',
            'background_image',
            'background_color',
            'message_default',
            'message_text',
            'last_update',
        ]
        params: list = [
            stored_screen.uniq_id,
            stored_screen.name,
            stored_screen.type,
            stored_screen.public,
            stored_screen.input_exit_button if stored_screen.type == 'input' else None,
            stored_screen.players_show_unpaired
            if stored_screen.type == 'players'
            else None,
            stored_screen.columns,
            stored_screen.font_size,
            stored_screen.menu_link if stored_screen.type != 'image' else None,
            stored_screen.menu_text if stored_screen.type != 'image' else None,
            stored_screen.menu if stored_screen.type != 'image' else None,
            stored_screen.timer_id,
            stored_screen.results_limit if stored_screen.type == 'results' else None,
            stored_screen.results_max_age if stored_screen.type == 'results' else None,
            self.dump_to_json_database_field(stored_screen.results_tournament_ids, [])
            if stored_screen.type == 'results'
            else None,
            stored_screen.ranking_crosstable
            if stored_screen.type == 'ranking'
            else False,
            stored_screen.ranking_round if stored_screen.type == 'ranking' else None,
            stored_screen.ranking_min_points
            if stored_screen.type == 'ranking'
            else None,
            stored_screen.ranking_max_points
            if stored_screen.type == 'ranking'
            else None,
            stored_screen.background_image if stored_screen.type == 'image' else None,
            stored_screen.background_color if stored_screen.type == 'image' else None,
            stored_screen.message_default,
            stored_screen.message_text,
            time.time(),
        ]
        if stored_screen.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `screen`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            screen_id = self._last_inserted_id()
            if screen_id is None:
                raise RuntimeError('Screen insertion failed')
            fetched_stored_screen = self.get_stored_screen(screen_id=screen_id)
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_screen.id]
            self.execute(
                f'UPDATE `screen` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_screen = self.get_stored_screen(screen_id=stored_screen.id)
        if fetched_stored_screen is None:
            raise RuntimeError('Screen write failed')
        self.set_last_update()
        return fetched_stored_screen

    def add_stored_screen(
        self,
        stored_screen: StoredScreen,
    ) -> StoredScreen:
        assert stored_screen.id is None, f'stored_screen.id={stored_screen.id}'
        return self._write_stored_screen(stored_screen)

    def update_stored_screen(
        self,
        stored_screen: StoredScreen,
    ) -> StoredScreen:
        assert stored_screen.id is not None
        return self._write_stored_screen(stored_screen)

    def _delete_screen_stored_screen_sets(self, screen_id: int):
        self.execute('DELETE FROM `screen_set` WHERE `screen_id` = ?;', (screen_id,))

    def delete_stored_screen(self, screen_id: int):
        self._delete_screen_stored_screen_sets(screen_id)
        self.execute('DELETE FROM `screen` WHERE `id` = ?;', (screen_id,))
        self.set_last_update()

    def _delete_tournament_stored_screens(self, tournament_id: int):
        self.execute(
            'SELECT `screen`.`id` AS `screen_id` '
            'FROM `screen` '
            'JOIN `screen_set` ON `screen_set`.`screen_id` = `screen`.`id` '
            'WHERE `screen_set`.`tournament_id` = ?',
            (tournament_id,),
        )
        for row in self.fetchall():
            self.delete_stored_screen(row['screen_id'])

    # ---------------------------------------------------------------------------------
    # StoredScreenSet
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _row_to_stored_screen_set(row: dict[str, Any]) -> StoredScreenSet:
        return StoredScreenSet(
            id=row['id'],
            screen_id=row['screen_id'],
            tournament_id=row['tournament_id'],
            order=row['order'],
            name=row['name'],
            fixed_boards_str=row['fixed_boards_str'],
            first=row['first'],
            last=row['last'],
            last_update=row['last_update'],
        )

    def get_stored_screen_set(self, screen_id: int) -> StoredScreenSet | None:
        self.execute(
            'SELECT * FROM `screen_set` WHERE `id` = ?',
            (screen_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_screen_set(row)
        return None

    def get_stored_screen_next_set_order(self, screen_id: int) -> int:
        self.execute(
            'SELECT MAX(`order`) AS order_max FROM `screen_set` WHERE `screen_id` = ?',
            (screen_id,),
        )
        row: dict[str, Any] = self.fetchone()
        return (row['order_max'] if row['order_max'] else 0) + 1

    def load_stored_screen_sets(self, screen_id: int) -> Iterator[StoredScreenSet]:
        self.execute(
            'SELECT * FROM `screen_set` WHERE `screen_id` = ? ORDER BY `order`',
            (screen_id,),
        )
        yield from map(self._row_to_stored_screen_set, self.fetchall())

    def reorder_stored_screen_sets(
        self,
        screen_id: int,
        screen_set_ids: list[int],
    ):
        order: int = 1
        for screen_set_id in screen_set_ids:
            self.execute(
                'UPDATE `screen_set` SET `order` = ?, `last_update` = ? WHERE `id` = ?',
                (
                    order,
                    time.time(),
                    screen_set_id,
                ),
            )
            order += 1
        self._set_stored_screen_last_update(screen_id)
        self.set_last_update()

    def _write_stored_screen_set(
        self,
        stored_screen_set: StoredScreenSet,
    ) -> StoredScreenSet:
        fields: list[str] = [
            'screen_id',
            'tournament_id',
            'name',
            'order',
            'fixed_boards_str',
            'first',
            'last',
            'last_update',
        ]
        params: list = [
            stored_screen_set.screen_id,
            stored_screen_set.tournament_id,
            stored_screen_set.name,
            stored_screen_set.order,
            stored_screen_set.fixed_boards_str,
            stored_screen_set.first,
            stored_screen_set.last,
            time.time(),
        ]
        if stored_screen_set.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `screen_set`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            screen_set_id: int | None = self._last_inserted_id()
            if screen_set_id is None:
                raise RuntimeError('Screen set insertion failed')
            fetched_stored_screen_set = self.get_stored_screen_set(
                screen_id=screen_set_id
            )
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_screen_set.id]
            self.execute(
                f'UPDATE `screen_set` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_screen_set = self.get_stored_screen_set(
                screen_id=stored_screen_set.id
            )
        if fetched_stored_screen_set is None:
            raise RuntimeError('Screen set write failed')
        self.set_last_update()
        return fetched_stored_screen_set

    def clone_stored_screen_set(
        self,
        screen_set_id: int,
        screen_id: int,
    ) -> StoredScreenSet:
        stored_screen_set = self.get_stored_screen_set(screen_set_id)
        assert stored_screen_set is not None
        stored_screen_set.id = None
        stored_screen_set.screen_id = screen_id
        stored_screen_set.last_update = time.time()
        stored_screen_set.order = self.get_stored_screen_next_set_order(
            stored_screen_set.screen_id
        )
        new_stored_screen_set: StoredScreenSet = self._write_stored_screen_set(
            stored_screen_set
        )
        return new_stored_screen_set

    def add_stored_screen_set(
        self,
        screen_id: int,
        tournament_id: int,
    ) -> StoredScreenSet:
        stored_screen_set: StoredScreenSet = StoredScreenSet(
            id=None,
            screen_id=screen_id,
            tournament_id=tournament_id,
            order=self.get_stored_screen_next_set_order(screen_id),
            name=None,
            fixed_boards_str=None,
            first=None,
            last=None,
        )
        return self._write_stored_screen_set(stored_screen_set)

    def update_stored_screen_set(
        self,
        stored_screen_set: StoredScreenSet,
    ) -> StoredScreenSet:
        assert stored_screen_set.id is not None
        return self._write_stored_screen_set(stored_screen_set)

    def delete_stored_screen_set(self, screen_set_id: int, screen_id: int):
        order: int = 1
        for stored_screen_set in self.load_stored_screen_sets(screen_id):
            self.execute(
                'UPDATE `screen_set` SET `order` = ?, `last_update` = ? WHERE `id` = ?',
                (
                    order,
                    time.time(),
                    stored_screen_set.id,
                ),
            )
            order += 1
        self._set_stored_screen_last_update(screen_id)
        self.execute('DELETE FROM `screen_set` WHERE `id` = ?;', (screen_set_id,))
        self.set_last_update()

    # ---------------------------------------------------------------------------------
    # StoredRotator
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_rotator(cls, row: dict[str, Any]) -> StoredRotator:
        return StoredRotator(
            id=row['id'],
            uniq_id=row['uniq_id'],
            public=cls.load_bool_from_database_field(row['public']),
            delay=row['delay'],
            message_default=cls.load_bool_from_database_field(row['message_default']),
            message_text=row['message_text'],
            screen_ids=cls.load_json_from_database_field(row['screen_ids']),
            family_ids=cls.load_json_from_database_field(row['family_ids']),
        )

    def get_stored_rotator(self, rotator_id: int) -> StoredRotator | None:
        self.execute(
            'SELECT * FROM `rotator` WHERE `id` = ?',
            (rotator_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_rotator(row)
        return None

    def load_stored_rotators(self) -> Iterator[StoredRotator]:
        self.execute(
            'SELECT * FROM `rotator` ORDER BY `uniq_id`',
            (),
        )
        yield from map(self._row_to_stored_rotator, self.fetchall())

    def _write_stored_rotator(
        self,
        stored_rotator: StoredRotator,
    ) -> StoredRotator:
        fields: list[str] = [
            'uniq_id',
            'public',
            'delay',
            'message_default',
            'message_text',
            'screen_ids',
            'family_ids',
        ]
        params: list = [
            stored_rotator.uniq_id,
            stored_rotator.public,
            stored_rotator.delay,
            stored_rotator.message_default,
            stored_rotator.message_text,
            self.dump_to_json_database_field(stored_rotator.screen_ids, []),
            self.dump_to_json_database_field(stored_rotator.family_ids, []),
        ]
        if stored_rotator.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `rotator`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            rotator_id: int | None = self._last_inserted_id()
            if rotator_id is None:
                raise RuntimeError('Rotator insertion failed')
            fetched_stored_rotator = self.get_stored_rotator(rotator_id=rotator_id)
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_rotator.id]
            self.execute(
                f'UPDATE `rotator` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_rotator = self.get_stored_rotator(stored_rotator.id)
        if fetched_stored_rotator is None:
            raise RuntimeError('Rotator write failed')
        self.set_last_update()
        return fetched_stored_rotator

    def add_stored_rotator(
        self,
        stored_rotator: StoredRotator,
    ) -> StoredRotator:
        assert stored_rotator.id is None
        return self._write_stored_rotator(stored_rotator)

    def update_stored_rotator(
        self,
        stored_rotator: StoredRotator,
    ) -> StoredRotator:
        assert stored_rotator.id is not None
        return self._write_stored_rotator(stored_rotator)

    def delete_stored_rotator(self, rotator_id: int):
        self.execute('DELETE FROM `rotator` WHERE `id` = ?;', (rotator_id,))
        self.set_last_update()

    # ---------------------------------------------------------------------------------
    # StoredClientController
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_client_controller(
        cls, row: dict[str, Any]
    ) -> StoredClientController:
        return StoredClientController(
            id=row['id'],
            uniq_id=row['uniq_id'],
            name=row['name'],
            screen_id=row['screen_id'],
            rotator_id=row['rotator_id'],
            public=cls.load_bool_from_database_field(row['public']),
        )

    def get_stored_client_controller(
        self, client_controller_id: int
    ) -> StoredClientController | None:
        self.execute(
            'SELECT * FROM `client_controller` WHERE `id` = ?',
            (client_controller_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_client_controller(row)
        return None

    def load_stored_client_controllers(
        self,
    ) -> Iterator[StoredClientController]:
        self.execute(
            'SELECT * FROM `client_controller` ORDER BY `uniq_id`',
            (),
        )
        yield from map(self._row_to_stored_client_controller, self.fetchall())

    def _write_stored_client_controller(
        self,
        stored_client_controller: StoredClientController,
    ) -> StoredClientController:
        fields: list[str] = [
            'uniq_id',
            'name',
            'public',
            'screen_id',
            'rotator_id',
            'last_update',
        ]
        params: list = [
            stored_client_controller.uniq_id,
            stored_client_controller.name,
            stored_client_controller.public,
            stored_client_controller.screen_id,
            stored_client_controller.rotator_id,
            time.time(),
        ]
        if stored_client_controller.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `client_controller`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            client_controller_id: int | None = self._last_inserted_id()
            if client_controller_id is None:
                raise RuntimeError('Client controller insertion failed')
            fetched_stored_client_controller = self.get_stored_client_controller(
                client_controller_id
            )
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_client_controller.id]
            self.execute(
                f'UPDATE `client_controller` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_client_controller = self.get_stored_client_controller(
                stored_client_controller.id
            )
        if fetched_stored_client_controller is None:
            raise RuntimeError('Client controller write failed')
        self.set_last_update()
        return fetched_stored_client_controller

    def add_stored_client_controller(
        self,
        stored_client_controller: StoredClientController,
    ) -> StoredClientController:
        assert stored_client_controller.id is None
        return self._write_stored_client_controller(stored_client_controller)

    def update_stored_client_controller(
        self,
        stored_client_controller: StoredClientController,
    ) -> StoredClientController:
        assert stored_client_controller.id is not None
        return self._write_stored_client_controller(stored_client_controller)

    def delete_stored_client_controller(self, client_controller_id: int):
        self.execute(
            'DELETE FROM `client_controller` WHERE `id` = ?;', (client_controller_id,)
        )
        self.set_last_update()
