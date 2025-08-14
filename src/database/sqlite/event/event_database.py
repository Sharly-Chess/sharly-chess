import shutil
import time
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime
from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import Any, TYPE_CHECKING, override, Self, cast

from packaging.version import Version

from common import format_timestamp_date, format_timestamp_time, DEVEL_ENV, EVENTS_DIR
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.event.event_store import (
    StoredDisplayController,
    StoredTournament,
    StoredEvent,
    EventMetadata,
    StoredTimer,
    StoredTimerHour,
    StoredFamily,
    StoredRotator,
    StoredScreenSet,
    StoredScreen,
    StoredPrizeGroup,
    StoredPrizeCategory,
    StoredPrizeCriterion,
    StoredPrize,
    StoredPlayer,
    StoredTournamentPlayer,
    StoredPairing,
    StoredBoard,
)
from database.sqlite.event import migrations
from database.sqlite.migration_database import MigrationDatabase
from plugins.manager import plugin_manager

if TYPE_CHECKING:
    from data.loader import EventBackup
    from database.sqlite.migration import DatabaseMigrationManager

logger: Logger = get_logger()


class EventDatabase(MigrationDatabase):
    """The SQLite database class for Sharly Chess events."""

    def __init__(
        self,
        uniq_id: str | None = None,
        write: bool = False,
        *,
        file_path: Path | None = None,
    ):
        """Initialize EventDatabase with either a unique ID or a file path."""
        if uniq_id is not None and file_path is not None:
            raise ValueError('Cannot specify both uniq_id and file_path')
        if uniq_id is None and file_path is None:
            raise ValueError('Must specify either uniq_id or file_path')

        if file_path is not None:
            # Initialize with file path
            self.uniq_id = file_path.stem
            self.update_event_loader = False
            super().__init__(file_path, write)
        else:
            # Traditional initialization with uniq_id
            assert uniq_id is not None
            self.uniq_id = uniq_id
            self.update_event_loader = True
            super().__init__(self.event_database_path(self.uniq_id), write)

    def __exit__(self, exc_type, exc_value, traceback):
        super().__exit__(exc_type, exc_value, traceback)

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
        return EVENTS_DIR / f'{uniq_id}.{SharlyChessConfig.event_database_ext}'

    @classmethod
    def database_modified_timestamp(cls, uniq_id: str) -> float:
        return cls.event_database_path(uniq_id).lstat().st_mtime

    def delete(self) -> Path:
        """Soft-deletes the event database file by archiving it."""
        from data.loader import EventLoader

        file: Path = EventDatabase(self.uniq_id).file
        index: int = 0
        date_str: str = datetime.strftime(datetime.now(), '%Y-%m-%d-%H-%M')
        arch: Path = (
            file.parent
            / f'{file.stem}_{date_str}.{SharlyChessConfig.event_archive_ext}'
        )
        while True:
            try:
                file.rename(arch)
                logger.info('Database has been archived (%s).', arch)
                EventLoader.unload_all_events()
                return arch
            except FileExistsError:
                logger.warning(
                    'Could not rename the database because file [%s] already exists.',
                    arch,
                )
                index += 1
                arch = file.parent / f'{file.stem}_{date_str}-{index}.arch'

    def rename(self, new_uniq_id: str):
        """Changes the event file database to the one associated to the
        provided `new_uniq_id`."""

        from data.loader import EventLoader

        self.file.rename(EventDatabase(new_uniq_id).file)
        EventLoader.unload_all_events()

    def clone(self, new_uniq_id: str):
        """Create a copy of the event database file corresponding to an event
        with name `new_uniq_id`."""
        from data.loader import EventLoader

        shutil.copy(self.file, EventDatabase(new_uniq_id).file)
        EventLoader.unload_all_events()

    def create_backup(self) -> 'EventBackup':
        """Creates a backup of the event database.
        If a backup already exists for the same version, overwrite it."""
        from data.loader import EventBackup

        backup = EventBackup(self.uniq_id, self.get_version())
        backup.file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.file, backup.file)
        return backup

    # ---------------------------------------------------------------------------------
    # Utils
    # ---------------------------------------------------------------------------------

    @classmethod
    def dump_to_json_database_timer_colors(cls, colors) -> str | None:
        """Serializes the timer colors into JSON.
        By default, returns a serialization of {i: None} (i in (1, 2, 3))."""
        return cls.dump_to_json_database_field(colors, {i: None for i in range(1, 4)})

    @classmethod
    def dump_to_json_database_timer_delays(cls, delays) -> str | None:
        """Serializes the timer delays into JSON.
        By default, returns a serialization of {i: None} (i in (1, 2, 3))."""
        return cls.dump_to_json_database_field(delays, {i: None for i in range(1, 4)})

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

    def _row_to_base_stored_event[T: StoredEvent | EventMetadata](
        self, row: dict[str, Any], stored_event_type: type[T]
    ) -> T:
        """Convert a row to a StoredEvent record."""
        stored_event = stored_event_type(
            uniq_id=self.uniq_id,
            name=row['name'],
            federation=row.get('federation', SharlyChessConfig().default_federation),
            start=row['start'],
            stop=row['stop'],
            public=self.load_bool_from_database_field(row['public']),
            location=row['location'],
            hide_background_image=self.load_bool_from_database_field(
                row.get(
                    'hide_background_image',
                    SharlyChessConfig.default_hide_background_image,
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
            prize_currency=row['prize_currency'],
        )
        plugin_manager.hook.augment_event_after_db_fetch(
            stored_event=stored_event, row=row
        )
        return cast(T, stored_event)

    def load_stored_event(self) -> StoredEvent:
        self.execute('SELECT * FROM `info`')
        stored_event: StoredEvent = self._row_to_base_stored_event(
            self.fetchone(), StoredEvent
        )
        stored_event.stored_tournaments = self.load_stored_tournaments()
        stored_event.stored_timers = list(self.load_stored_timers())
        stored_event.stored_families = list(self.load_stored_families())
        stored_event.stored_screens = list(self.load_stored_screens())
        stored_event.stored_rotators = list(self.load_stored_rotators())
        stored_event.stored_display_controllers = list(
            self.load_stored_display_controllers()
        )
        return stored_event

    def load_stored_event_metadata(self) -> EventMetadata:
        self.execute('SELECT * FROM `info`')
        metadata: EventMetadata = self._row_to_base_stored_event(
            self.fetchone(), EventMetadata
        )
        metadata.tournament_count = self._get_table_count('tournament')
        metadata.player_count = self._get_table_count('player')
        metadata.timer_count = self._get_table_count('timer')
        metadata.screen_count = self._get_table_count('screen')
        metadata.family_count = self._get_table_count('family')
        metadata.rotator_count = self._get_table_count('rotator')
        return metadata

    def update_stored_event(self, stored_event: StoredEvent):
        """Updates the event database with the information in the provided
        `stored_event`."""

        per_plugin_event_data = plugin_manager.hook.event_data_for_db_write(
            stored_event=stored_event
        )
        plugin_data = {
            key: value for data in per_plugin_event_data for key, value in data.items()
        }

        fields = (
            self._get_fields_dict(
                stored_event,
                [
                    'name',
                    'start',
                    'stop',
                    'public',
                    'federation',
                    'location',
                    'hide_background_image',
                    'background_image',
                    'background_color',
                    'update_password',
                    'record_illegal_moves',
                    'rules',
                    'message_text',
                    'message_color',
                    'message_background_color',
                    'prize_currency',
                ],
            )
            | {
                'timer_colors': self.dump_to_json_database_timer_colors(
                    stored_event.timer_colors
                ),
                'timer_delays': self.dump_to_json_database_timer_delays(
                    stored_event.timer_delays
                ),
            }
            | plugin_data
        )

        field_sets = (f'`{f}` = ?' for f in fields.keys())
        self.execute(
            f'UPDATE `info` SET {", ".join(field_sets)}', tuple(fields.values())
        )

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
        # NOTE (Molrn) The table definition of `family` and `screen` are missing
        # the `ON DELETE SET NULL` clause, so it has to be done manually
        self.execute(
            'UPDATE `family` SET `timer_id` = NULL WHERE `timer_id` = ?;', (timer_id,)
        )
        self.execute(
            'UPDATE `screen` SET `timer_id` = NULL WHERE `timer_id` = ?;', (timer_id,)
        )
        self.execute('DELETE FROM `timer` WHERE id = ?;', (timer_id,))

    # ---------------------------------------------------------------------------------
    # StoredTournament
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_tournament(cls, row: dict[str, Any]) -> StoredTournament:
        stored_tournament = StoredTournament(
            id=row['id'],
            uniq_id=row['uniq_id'],
            name=row['name'],
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
            pairing=row['pairing'],
            pairing_settings=cls.load_json_from_database_field(row['pairing_settings']),
            current_round=row['current_round'],
            check_in_open=cls.load_bool_from_database_field(row['check_in_open']),
            rounds=row['rounds'],
            rating=row['rating'],
            last_update=row['last_update'],
            last_result_update=row['last_result_update'],
            last_illegal_move_update=row['last_illegal_move_update'],
            last_check_in_update=row['last_check_in_update'],
            last_pairing_update=row['last_pairing_update'],
            last_player_update=row['last_player_update'],
            tie_breaks=cls.load_json_from_database_field(row['tie_breaks']),
            start=row['start'],
            stop=row['stop'],
            location=row['location'],
            three_points_for_a_win=cls.load_bool_from_database_field(
                row['three_points_for_a_win']
            ),
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

    def load_stored_tournaments(self) -> list[StoredTournament]:
        self.execute('SELECT * FROM `tournament` ORDER BY `uniq_id`')
        stored_tournaments: list[StoredTournament] = []
        for row in self.fetchall():
            stored_tournament = self._row_to_stored_tournament(row)
            id_ = stored_tournament.id
            assert id_ is not None
            stored_tournament.stored_prize_groups = (
                self.load_tournament_stored_prize_groups(id_)
            )
            stored_tournament.stored_players = self.load_tournament_stored_players(id_)
            stored_tournament.stored_boards_by_round = (
                self.load_tournament_stored_boards_by_round(id_)
            )
            stored_tournaments.append(stored_tournament)
        return stored_tournaments

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

        fields = (
            self._get_fields_dict(
                stored_tournament,
                [
                    'uniq_id',
                    'name',
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
                    'rounds',
                    'rating',
                    'pairing',
                    'location',
                    'start',
                    'stop',
                    'last_rounds_no_byes',
                    'three_points_for_a_win',
                ],
            )
            | {
                'tie_breaks': self.dump_to_json_database_field(
                    stored_tournament.tie_breaks
                ),
                'last_update': time.time(),
            }
            | plugin_data
        )

        if stored_tournament.id is None:
            fields_str = ', '.join(f'`{f}`' for f in fields)
            values_str = ', '.join(['?'] * len(fields))
            self.execute(
                f'INSERT INTO `tournament`({fields_str}) VALUES ({values_str})',
                tuple(fields.values()),
            )
            tournament_id: int | None = self._last_inserted_id()
            if tournament_id is None:
                raise RuntimeError('Tournament insertion failed')
            fetched_stored_tournament = self.get_stored_tournament(tournament_id)
        else:
            field_sets = ', '.join(f'`{f}` = ?' for f in fields)
            self.execute(
                f'UPDATE `tournament` SET {field_sets} WHERE `id` = ?',
                tuple(fields.values()) + (stored_tournament.id,),
            )
            fetched_stored_tournament = self.get_stored_tournament(stored_tournament.id)
        if fetched_stored_tournament is None:
            raise RuntimeError('Tournament write failed')
        return fetched_stored_tournament

    def add_stored_tournament(
        self,
        stored_tournament: StoredTournament,
    ) -> StoredTournament:
        assert stored_tournament.id is None, f'{stored_tournament.id=}'
        return self._write_stored_tournament(stored_tournament)

    def update_stored_tournament(
        self,
        stored_tournament: StoredTournament,
    ) -> StoredTournament:
        assert stored_tournament.id is not None
        return self._write_stored_tournament(stored_tournament)

    def delete_stored_tournament(self, tournament_id: int):
        self.execute('DELETE FROM `tournament` WHERE `id` = ?;', (tournament_id,))

    def _set_tournament_timestamp_field(self, field_: str, tournament_id: int) -> float:
        # TODO (Molrn) replace all these usages with the appropriate SQL triggers
        timestamp = time.time()
        # FIXME(Amaras): This can can be a SQL injection attack vector.
        # As such, it needs to be eliminated as quickly as possible.
        self.execute(
            f'UPDATE `tournament` SET `{field_}` = ? WHERE `id` = ?',
            (
                timestamp,
                tournament_id,
            ),
        )
        return timestamp

    def set_tournament_last_illegal_move_update(self, tournament_id: int) -> float:
        return self._set_tournament_timestamp_field(
            'last_illegal_move_update', tournament_id
        )

    def set_tournament_last_check_in_update(self, tournament_id: int) -> float:
        return self._set_tournament_timestamp_field(
            'last_check_in_update', tournament_id
        )

    def set_tournament_last_result_update(self, tournament_id: int) -> float:
        return self._set_tournament_timestamp_field('last_result_update', tournament_id)

    def set_tournament_last_pairing_update(self, tournament_id: int) -> float:
        return self._set_tournament_timestamp_field(
            'last_pairing_update', tournament_id
        )

    def set_tournament_last_player_update(self, tournament_id: int) -> float:
        return self._set_tournament_timestamp_field('last_player_update', tournament_id)

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

    def set_tournament_pairing_settings(
        self, tournament_id: int, pairing_settings: dict[str, Any]
    ):
        self.execute(
            'UPDATE `tournament` SET '
            '`pairing_settings` = ?, `last_update` = ? '
            'WHERE `id` = ?',
            (
                self.dump_to_json_database_field(pairing_settings),
                time.time(),
                tournament_id,
            ),
        )

    def set_tournament_current_round(self, tournament_id: int, current_round: int):
        self.execute(
            'UPDATE `tournament` SET '
            '`current_round` = ?, `last_update` = ? '
            'WHERE `id` = ?',
            (
                current_round,
                time.time(),
                tournament_id,
            ),
        )

    # ---------------------------------------------------------------------------------
    # StoredPlayer
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_player(cls, row: dict[str, Any]) -> StoredPlayer:
        return StoredPlayer(
            id=row['id'],
            last_name=row['last_name'],
            first_name=row['first_name'],
            date_of_birth=cls.load_date_from_database_field(row['date_of_birth']),
            gender=row['gender'],
            mail=row['mail'],
            phone=row['phone'],
            comment=row['comment'],
            owed=row['owed'],
            paid=row['paid'],
            title=row['title'],
            ratings=cls.set_dict_int_keys(
                cls.load_json_from_database_field(row['ratings'])
            )
            or {},
            fide_id=row['fide_id'],
            federation=row['federation'],
            club=row['club'],
            fixed=row['fixed'],
            check_in=row['check_in'],
            plugin_data=cls.load_json_from_database_field(row['plugin_data']),
        )

    def load_tournament_stored_players(self, tournament_id: int) -> list[StoredPlayer]:
        self.execute(
            (
                'SELECT `player`.* FROM `player` '
                'INNER JOIN `tournament_player` ON `player`.`id` = `player_id`'
                'WHERE `tournament_id` = ?'
            ),
            (tournament_id,),
        )
        stored_players: list[StoredPlayer] = []
        for row in self.fetchall():
            player = self._row_to_stored_player(row)
            assert player.id is not None
            player.stored_tournament_player = self.load_player_stored_tournament_player(
                player.id
            )
            stored_players.append(player)
        return stored_players

    @classmethod
    def _get_player_fields_dict(cls, stored_player: StoredPlayer) -> dict[str, Any]:
        return cls._get_fields_dict(
            stored_player,
            [
                'first_name',
                'last_name',
                'gender',
                'mail',
                'phone',
                'comment',
                'owed',
                'paid',
                'title',
                'fide_id',
                'federation',
                'club',
                'fixed',
            ],
        ) | {
            'date_of_birth': cls.dump_date_to_database_field(
                stored_player.date_of_birth
            ),
            'ratings': cls.dump_to_json_database_field(stored_player.ratings),
            'plugin_data': cls.dump_to_json_database_field(stored_player.plugin_data),
        }

    def add_stored_player(
        self,
        stored_player: StoredPlayer,
    ) -> int:
        fields = self._get_player_fields_dict(stored_player)
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `player`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        if not (player_id := self._last_inserted_id()):
            raise RuntimeError('Player insertion failed')
        return player_id

    def update_stored_player(self, stored_player: StoredPlayer):
        fields = self._get_player_fields_dict(stored_player)
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            f'UPDATE `player` SET {field_sets} WHERE `id` = ?',
            tuple(fields.values()) + (stored_player.id,),
        )

    def delete_stored_player(self, player_id: int):
        self.execute('DELETE FROM `player` WHERE `id` = ?;', (player_id,))

    def set_player_check_in(self, player_id: int, check_in: bool):
        self.execute(
            'UPDATE `player` SET `check_in` = ? WHERE `id` = ?',
            (check_in, player_id),
        )

    def set_players_check_in(self, player_ids: list[int], check_in: bool):
        list_set = ', '.join(['?'] * len(player_ids))
        self.execute(
            f'UPDATE `player` SET `check_in` = ? WHERE `id` IN ({list_set})',
            (check_in,) + tuple(player_ids),
        )

    def delete_players_personal_data(self):
        """Delete all personal data (email and phone number) from the database."""
        self.execute(
            'UPDATE `player` SET `phone` = ?, `mail`= ?',
            (
                '',
                '',
            ),
        )

    def delete_all_stored_players(self):
        self.execute('DELETE FROM `player`')

    # ---------------------------------------------------------------------------------
    # StoredTournamentPlayer
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_tournament_player(
        cls, row: dict[str, Any]
    ) -> StoredTournamentPlayer:
        return StoredTournamentPlayer(
            tournament_id=row['tournament_id'],
            player_id=row['player_id'],
            pairing_number=row['pairing_number'],
        )

    def load_player_stored_tournament_player(
        self, player_id: int
    ) -> StoredTournamentPlayer:
        self.execute(
            'SELECT * FROM `tournament_player` WHERE `player_id` = ?',
            (player_id,),
        )
        tournament_player = self._row_to_stored_tournament_player(self.fetchone())
        tournament_player.stored_pairings = self.load_tournament_player_stored_pairings(
            tournament_player.tournament_id, player_id
        )
        return tournament_player

    def add_stored_tournament_player(
        self, stored_tournament_player: StoredTournamentPlayer
    ):
        fields = self._get_fields_dict(
            stored_tournament_player, ['tournament_id', 'player_id', 'pairing_number']
        )
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `tournament_player`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        for stored_pairing in stored_tournament_player.stored_pairings:
            self.add_stored_pairing(stored_pairing)

    def set_tournament_player_pairing_number(
        self, stored_tournament_player: StoredTournamentPlayer
    ):
        self.execute(
            (
                'UPDATE `tournament_player` SET `pairing_number` = ? '
                'WHERE `tournament_id` = ? AND `player_id` = ?'
            ),
            (
                stored_tournament_player.pairing_number,
                stored_tournament_player.tournament_id,
                stored_tournament_player.player_id,
            ),
        )

    def delete_stored_tournament_player(self, tournament_id: int, player_id: int):
        self.execute(
            (
                'DELETE FROM `tournament_player` '
                'WHERE `tournament_id` = ? AND `player_id` = ?'
            ),
            (tournament_id, player_id),
        )
        self.execute(
            'DELETE FROM `pairing` WHERE `tournament_id` = ? AND `player_id` = ?',
            (tournament_id, player_id),
        )

    # ---------------------------------------------------------------------------------
    # StoredPairings
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_pairing(cls, row: dict[str, Any]) -> StoredPairing:
        return StoredPairing(
            tournament_id=row['tournament_id'],
            player_id=row['player_id'],
            round_=row['round'],
            result=row['result'],
            board_id=row['board_id'],
            illegal_moves=row['illegal_moves'],
        )

    def load_tournament_player_stored_pairings(
        self, tournament_id: int, player_id: int
    ) -> list[StoredPairing]:
        self.execute(
            (
                'SELECT * FROM `pairing` '
                'WHERE `tournament_id` = ? AND `player_id` = ? '
                'ORDER BY `round`'
            ),
            (tournament_id, player_id),
        )
        return [self._row_to_stored_pairing(row) for row in self.fetchall()]

    def add_stored_pairing(
        self,
        stored_pairing: StoredPairing,
    ):
        fields = self._get_fields_dict(
            stored_pairing,
            ['tournament_id', 'player_id', 'result', 'board_id', 'illegal_moves'],
        ) | {'round': stored_pairing.round_}
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `pairing`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )

    def update_stored_pairing(self, stored_pairing: StoredPairing):
        fields = self._get_fields_dict(
            stored_pairing, ['result', 'board_id', 'illegal_moves']
        )
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            (
                f'UPDATE `pairing` SET {field_sets} '
                'WHERE `tournament_id` = ? AND `player_id` = ? AND `round` = ?'
            ),
            tuple(fields.values())
            + (
                stored_pairing.tournament_id,
                stored_pairing.player_id,
                stored_pairing.round_,
            ),
        )

    def delete_stored_pairing(self, stored_pairing: StoredPairing):
        self.execute(
            (
                'DELETE FROM `pairing` '
                'WHERE `tournament_id` = ? AND `player_id` = ? AND `round` = ?'
            ),
            (
                stored_pairing.tournament_id,
                stored_pairing.player_id,
                stored_pairing.round_,
            ),
        )

    # ---------------------------------------------------------------------------------
    # StoredBoard
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_board(cls, row: dict[str, Any]) -> StoredBoard:
        return StoredBoard(
            id=row['id'],
            white_player_id=row['white_player_id'],
            black_player_id=row['black_player_id'],
            index=row['index'],
            last_result_update=row['last_result_update'],
        )

    def load_tournament_stored_boards_by_round(
        self, tournament_id: int
    ) -> dict[int, list[StoredBoard]]:
        self.execute(
            (
                'SELECT `board`.*, `pairing`.`round` '
                'FROM `board` INNER JOIN `pairing` '
                'ON `board`.`id` = `pairing`.`board_id` '
                'WHERE `pairing`.`tournament_id` = ? '
                'ORDER BY `pairing`.`round`, `board`.`index`'
            ),
            (tournament_id,),
        )
        stored_boards_by_round: dict[int, list[StoredBoard]] = {}
        for row in self.fetchall():
            board = self._row_to_stored_board(row)
            round_ = row['round']
            if round_ in stored_boards_by_round:
                stored_boards_by_round[round_].append(board)
            else:
                stored_boards_by_round[round_] = [board]
        return stored_boards_by_round

    def add_stored_board(self, stored_board: StoredBoard) -> int:
        fields = self._get_fields_dict(
            stored_board, ['white_player_id', 'black_player_id', 'index']
        )
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `board`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        if not (board_id := self._last_inserted_id()):
            raise RuntimeError('Board insertion failed')
        return board_id

    def update_stored_board(self, stored_board: StoredBoard):
        fields = self._get_fields_dict(
            stored_board, ['white_player_id', 'black_player_id', 'index']
        )
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            f'UPDATE `board` SET {field_sets} WHERE `id` = ?',
            tuple(fields.values()) + (stored_board.id,),
        )

    def delete_stored_board(self, board_id: int):
        self.execute('DELETE FROM `board` WHERE `id` = ?;', (board_id,))

    def update_board_last_result_update(
        self, board_id: int, clear: bool = False
    ) -> float | None:
        """Updates board timestamp"""

        if clear:
            self.execute(
                'UPDATE `board` SET `last_result_update` = NULL WHERE `id` = ?',
                (board_id,),
            )
            return None
        else:
            date = time.time()

            self.execute(
                'UPDATE `board` SET `last_result_update` = ? WHERE `id` = ?',
                (date, board_id),
            )

            return date

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
            players_show_opponent=cls.load_bool_or_none_from_database_field(
                row.get('players_show_opponent', None)
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
            'players_show_opponent',
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
            stored_family.players_show_opponent,
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
            players_show_opponent=cls.load_bool_or_none_from_database_field(
                row['players_show_opponent']
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
            'players_show_opponent',
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
            stored_screen.players_show_opponent
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

    def delete_stored_screen(self, screen_id: int):
        self.execute('DELETE FROM `screen` WHERE `id` = ?;', (screen_id,))

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

    # ---------------------------------------------------------------------------------
    # StoredDisplayController
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_display_controller(
        cls, row: dict[str, Any]
    ) -> StoredDisplayController:
        return StoredDisplayController(
            id=row['id'],
            uniq_id=row['uniq_id'],
            name=row['name'],
            screen_id=row['screen_id'],
            rotator_id=row['rotator_id'],
            public=cls.load_bool_from_database_field(row['public']),
        )

    def get_stored_display_controller(
        self, display_controller_id: int
    ) -> StoredDisplayController | None:
        self.execute(
            'SELECT * FROM `display_controller` WHERE `id` = ?',
            (display_controller_id,),
        )
        row: dict[str, Any]
        if row := self.fetchone():
            return self._row_to_stored_display_controller(row)
        return None

    def load_stored_display_controllers(
        self,
    ) -> Iterator[StoredDisplayController]:
        self.execute(
            'SELECT * FROM `display_controller` ORDER BY `uniq_id`',
            (),
        )
        yield from map(self._row_to_stored_display_controller, self.fetchall())

    def _write_stored_display_controller(
        self,
        stored_display_controller: StoredDisplayController,
    ) -> StoredDisplayController:
        fields: list[str] = [
            'uniq_id',
            'name',
            'public',
            'screen_id',
            'rotator_id',
            'last_update',
        ]
        params: list = [
            stored_display_controller.uniq_id,
            stored_display_controller.name,
            stored_display_controller.public,
            stored_display_controller.screen_id,
            stored_display_controller.rotator_id,
            time.time(),
        ]
        if stored_display_controller.id is None:
            protected_fields = [f'`{f}`' for f in fields]
            self.execute(
                f'INSERT INTO `display_controller`({", ".join(protected_fields)}) VALUES ({", ".join(["?"] * len(fields))})',
                tuple(params),
            )
            display_controller_id: int | None = self._last_inserted_id()
            if display_controller_id is None:
                raise RuntimeError('Display controller insertion failed')
            fetched_stored_display_controller = self.get_stored_display_controller(
                display_controller_id
            )
        else:
            field_sets = [f'`{f}` = ?' for f in fields]
            params += [stored_display_controller.id]
            self.execute(
                f'UPDATE `display_controller` SET {", ".join(field_sets)} WHERE `id` = ?',
                tuple(params),
            )
            fetched_stored_display_controller = self.get_stored_display_controller(
                stored_display_controller.id
            )
        if fetched_stored_display_controller is None:
            raise RuntimeError('Display controller write failed')
        return fetched_stored_display_controller

    def add_stored_display_controller(
        self,
        stored_display_controller: StoredDisplayController,
    ) -> StoredDisplayController:
        assert stored_display_controller.id is None
        return self._write_stored_display_controller(stored_display_controller)

    def update_stored_display_controller(
        self,
        stored_display_controller: StoredDisplayController,
    ) -> StoredDisplayController:
        assert stored_display_controller.id is not None
        return self._write_stored_display_controller(stored_display_controller)

    def delete_stored_display_controller(self, display_controller_id: int):
        self.execute(
            'DELETE FROM `display_controller` WHERE `id` = ?;', (display_controller_id,)
        )

    # ---------------------------------------------------------------------------------
    # StoredPrizeGroup
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_prize_group(cls, row: dict[str, Any]) -> StoredPrizeGroup:
        return StoredPrizeGroup(
            id=row['id'],
            tournament_id=row['tournament_id'],
            name=row['name'],
        )

    def load_tournament_stored_prize_groups(
        self, tournament_id: int
    ) -> list[StoredPrizeGroup]:
        self.execute(
            'SELECT * FROM `prize_group` WHERE `tournament_id` = ?',
            (tournament_id,),
        )
        stored_prize_groups: list[StoredPrizeGroup] = []
        for row in self.fetchall():
            prize_group = self._row_to_stored_prize_group(row)
            assert prize_group.id is not None
            prize_group.stored_prize_categories = (
                self.load_prize_group_stored_prize_categories(prize_group.id)
            )
            stored_prize_groups.append(prize_group)
        return stored_prize_groups

    def add_stored_prize_group(self, stored_prize_group: StoredPrizeGroup) -> int:
        fields = self._get_fields_dict(stored_prize_group, ['tournament_id', 'name'])
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `prize_group`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        if not (prize_group_id := self._last_inserted_id()):
            raise RuntimeError('Prize group insertion failed')
        return prize_group_id

    def update_stored_prize_group(self, stored_prize_group: StoredPrizeGroup):
        fields = self._get_fields_dict(stored_prize_group, ['tournament_id', 'name'])
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            f'UPDATE `prize_group` SET {field_sets} WHERE `id` = ?',
            tuple(fields.values()) + (stored_prize_group.id,),
        )

    def delete_stored_prize_group(self, prize_group_id: int):
        self.execute('DELETE FROM `prize_group` WHERE `id` = ?;', (prize_group_id,))

    # ---------------------------------------------------------------------------------
    # StoredPrizeCategory
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_prize_category(cls, row: dict[str, Any]) -> StoredPrizeCategory:
        return StoredPrizeCategory(
            id=row['id'],
            prize_group_id=row['prize_group_id'],
            name=row['name'],
            prize_sharing=row['prize_sharing'],
            sharing_threshold=row['sharing_threshold'],
            is_main=cls.load_bool_from_database_field(row['is_main']),
            index=row['index'],
        )

    def load_prize_group_stored_prize_categories(
        self, prize_group_id: int
    ) -> list[StoredPrizeCategory]:
        self.execute(
            'SELECT * FROM `prize_category` WHERE `prize_group_id` = ?',
            (prize_group_id,),
        )
        stored_prize_categories: list[StoredPrizeCategory] = []
        for row in self.fetchall():
            prize_category = self._row_to_stored_prize_category(row)
            assert prize_category.id is not None
            prize_category.stored_prize_criteria = (
                self.load_prize_category_stored_prize_criteria(prize_category.id)
            )
            prize_category.stored_prizes = self.load_prize_category_stored_prizes(
                prize_category.id
            )
            stored_prize_categories.append(prize_category)
        return stored_prize_categories

    def add_stored_prize_category(
        self,
        stored_prize_category: StoredPrizeCategory,
    ) -> int:
        fields = self._get_fields_dict(
            stored_prize_category,
            [
                'prize_group_id',
                'name',
                'prize_sharing',
                'sharing_threshold',
                'is_main',
                'index',
            ],
        )
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `prize_category`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        if not (prize_category_id := self._last_inserted_id()):
            raise RuntimeError('Prize category insertion failed')
        return prize_category_id

    def update_stored_prize_category(
        self,
        stored_prize_category: StoredPrizeCategory,
    ):
        fields = self._get_fields_dict(
            stored_prize_category,
            ['prize_group_id', 'name', 'prize_sharing', 'sharing_threshold', 'is_main'],
        )
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            f'UPDATE `prize_category` SET {field_sets} WHERE `id` = ?',
            tuple(fields.values()) + (stored_prize_category.id,),
        )

    def update_stored_prize_category_index(self, prize_category_id: int, index: int):
        self.execute(
            'UPDATE `prize_category` SET `index` = ? WHERE `id` = ?',
            (index, prize_category_id),
        )

    def delete_stored_prize_category(self, prize_category_id: int):
        self.execute(
            'DELETE FROM `prize_category` WHERE `id` = ?;', (prize_category_id,)
        )

    # ---------------------------------------------------------------------------------
    # StoredPrizeCriterion
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_prize_criterion(
        cls, row: dict[str, Any]
    ) -> StoredPrizeCriterion:
        return StoredPrizeCriterion(
            id=row['id'],
            prize_category_id=row['prize_category_id'],
            type=row['type'],
            options=cls.load_json_from_database_field(row['options']),
        )

    def load_prize_category_stored_prize_criteria(
        self, prize_category_id: int
    ) -> list[StoredPrizeCriterion]:
        self.execute(
            'SELECT * FROM `prize_criterion` WHERE `prize_category_id` = ?',
            (prize_category_id,),
        )
        return [self._row_to_stored_prize_criterion(row) for row in self.fetchall()]

    def add_stored_prize_criterion(
        self,
        stored_prize_criterion: StoredPrizeCriterion,
    ) -> int:
        fields = self._get_fields_dict(
            stored_prize_criterion, ['prize_category_id', 'type']
        ) | {
            'options': self.dump_to_json_database_field(stored_prize_criterion.options)
        }
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `prize_criterion`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        if not (prize_criterion_id := self._last_inserted_id()):
            raise RuntimeError('Prize criterion insertion failed')
        return prize_criterion_id

    def update_stored_prize_criterion(
        self,
        stored_prize_criterion: StoredPrizeCriterion,
    ):
        fields = self._get_fields_dict(
            stored_prize_criterion, ['prize_category_id', 'type']
        ) | {
            'options': self.dump_to_json_database_field(stored_prize_criterion.options)
        }
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            f'UPDATE `prize_criterion` SET {field_sets} WHERE `id` = ?',
            tuple(fields.values()) + (stored_prize_criterion.id,),
        )

    def delete_stored_prize_criterion(self, prize_criterion_id: int):
        self.execute(
            'DELETE FROM `prize_criterion` WHERE `id` = ?;', (prize_criterion_id,)
        )

    # ---------------------------------------------------------------------------------
    # StoredPrize
    # ---------------------------------------------------------------------------------

    @classmethod
    def _row_to_stored_prize(cls, row: dict[str, Any]) -> StoredPrize:
        return StoredPrize(
            id=row['id'],
            prize_category_id=row['prize_category_id'],
            value=row['value'],
            is_monetary=cls.load_bool_from_database_field(row['is_monetary']),
            description=row['description'],
        )

    def load_prize_category_stored_prizes(
        self, prize_category_id: int
    ) -> list[StoredPrize]:
        self.execute(
            'SELECT * FROM `prize` WHERE `prize_category_id` = ?',
            (prize_category_id,),
        )
        return [self._row_to_stored_prize(row) for row in self.fetchall()]

    def add_stored_prize(
        self,
        stored_prize: StoredPrize,
    ) -> int:
        fields = self._get_fields_dict(
            stored_prize,
            ['prize_category_id', 'value', 'is_monetary', 'description'],
        )
        fields_str = ', '.join(f'`{f}`' for f in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `prize`({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        if not (prize_id := self._last_inserted_id()):
            raise RuntimeError('Prize entry insertion failed')
        return prize_id

    def update_stored_prize(
        self,
        stored_prize: StoredPrize,
    ):
        fields = self._get_fields_dict(
            stored_prize,
            ['prize_category_id', 'value', 'is_monetary', 'description'],
        )
        field_sets = ', '.join(f'`{f}` = ?' for f in fields)
        self.execute(
            f'UPDATE `prize` SET {field_sets} WHERE `id` = ?',
            tuple(fields.values()) + (stored_prize.id,),
        )

    def delete_stored_prize(self, prize_id: int):
        self.execute('DELETE FROM `prize` WHERE `id` = ?;', (prize_id,))
