from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import Any, TYPE_CHECKING, ClassVar

from packaging.version import Version

from common import EVENTS_DIR
from common.exception import SharlyChessException
from common.logger import get_logger
from database.sqlite.config import migrations
from database.sqlite.config.config_store import (
    StoredConfig,
    StoredPlugin,
    StoredLocalSourceDatabase,
    StoredPlayerCategorySet,
)
from database.sqlite.migration_database import MigrationDatabase

if TYPE_CHECKING:
    from database.sqlite.migration import DatabaseMigrationManager

logger: Logger = get_logger()


class ConfigDatabase(MigrationDatabase):
    """The SQLite database class for Sharly Chess config."""

    # The name of the file holding the configuration of the application.
    config_database_name: ClassVar[str] = '.scc'
    # The file holding the configuration of the application.
    config_database_path: ClassVar[Path] = EVENTS_DIR / config_database_name
    is_setup = False

    def __init__(self, write: bool = False, enable_foreign_keys: bool = True):
        super().__init__(
            self.config_database_path,
            write,
            enable_foreign_keys=enable_foreign_keys,
        )
        if not self.is_setup:
            self.__class__.is_setup = True
            self.setup()

    @cached_property
    def migration_managers(self) -> list['DatabaseMigrationManager']:
        from database.sqlite.migration import DatabaseMigrationManager

        return [DatabaseMigrationManager(self, migrations)]

    @property
    def migration_by_legacy_version(self) -> dict[Version, str]:
        return {
            Version('2.4.24'): 'm001_create_info_table',
            Version('2.4.28'): 'm002_create_plugin_table',
            Version('2.4.30'): 'm003_create_local_source_database_table',
        }

    @property
    def log_prefix(self) -> str:
        return 'Config database - '

    @classmethod
    def setup(cls):
        """Setup the config database. If it does not exist, create it.
        If it is not up to date, update it."""
        database = cls()
        if not database.exists():
            database.create()
        else:
            try:
                status = database.check_status()
                if not status:
                    database.upgrade()
            except SharlyChessException as e:
                logger.exception(e)
                database.file.unlink(missing_ok=True)
                database.create()

    # ---------------------------------------------------------------------------------
    # StoredConfig
    # ---------------------------------------------------------------------------------

    def _row_to_stored_config(self, row: dict[str, Any]) -> StoredConfig:
        """Convert a row to a StoredConfig record."""
        return StoredConfig(
            force_edit=self.load_bool_from_database_field(row['force_edit']),
            console_log_level=row['console_log_level'],
            console_color=self.load_bool_from_database_field(row['console_color']),
            console_show_date=self.load_bool_from_database_field(
                row['console_show_date']
            ),
            console_show_level=self.load_bool_from_database_field(
                row['console_show_level']
            ),
            experimental=self.load_bool_from_database_field(row['experimental']),
            federation=row['federation'],
            launch_browser=self.load_bool_from_database_field(row['launch_browser']),
            locale=row['locale'],
            date_formatter=row['date_formatter'],
        )

    def _get_stored_config(self) -> StoredConfig:
        """Gets all the information about the config and returns a corresponding StoredConfig record."""
        self.execute('SELECT * FROM `info`')
        stored_config = self._row_to_stored_config(self.fetchone())
        stored_config.stored_player_category_sets = self.load_player_category_sets()
        return stored_config

    def load_stored_config(self) -> StoredConfig:
        return self._get_stored_config()

    def update_stored_config(self, stored_config: StoredConfig) -> StoredConfig:
        """Updates the config database with the information in the provided `stored_config`."""
        fields = self._get_fields_dict(
            stored_config,
            [
                'force_edit',
                'console_log_level',
                'console_color',
                'console_show_date',
                'console_show_level',
                'experimental',
                'launch_browser',
                'federation',
                'locale',
                'date_formatter',
            ],
        )
        field_sets = (f'`{f}` = ?' for f in fields.keys())
        self.execute(
            f'UPDATE `info` SET {", ".join(field_sets)}', tuple(fields.values())
        )
        return self._get_stored_config()

    # ---------------------------------------------------------------------------------
    # StoredPlugin
    # ---------------------------------------------------------------------------------

    def _row_to_stored_plugin(self, row: dict[str, Any]) -> StoredPlugin:
        return StoredPlugin(
            name=row['name'],
            is_enabled=self.load_bool_from_database_field(row['is_enabled']),
            plugin_data=self.load_json_from_database_field(row['plugin_data'], {}),
        )

    def load_stored_plugin(self, plugin_name: str) -> StoredPlugin | None:
        self.execute(
            'SELECT * FROM `plugin` WHERE `name` = ?',
            (plugin_name,),
        )
        if row := self.fetchone():
            return self._row_to_stored_plugin(row)
        return None

    def update_stored_plugin(self, stored_plugin: StoredPlugin) -> StoredPlugin | None:
        self.execute(
            'UPDATE `plugin` SET `is_enabled` = ?, `plugin_data` = ? WHERE `name` = ?',
            (
                stored_plugin.is_enabled,
                self.dump_to_json_database_field(stored_plugin.plugin_data),
                stored_plugin.name,
            ),
        )
        return self.load_stored_plugin(stored_plugin.name)

    def insert_stored_plugin(self, stored_plugin: StoredPlugin):
        fields = self._get_fields_dict(stored_plugin, ['name', 'is_enabled'])
        fields |= {
            'plugin_data': self.dump_to_json_database_field(
                stored_plugin.plugin_data, {}
            )
        }
        fields_str = ', '.join(f'`{field}`' for field in fields)
        self.execute(
            f'INSERT INTO `plugin` ({fields_str}) '
            f'VALUES ({", ".join(["?"] * len(fields))})',
            tuple(fields.values()),
        )

    # ---------------------------------------------------------------------------------
    # StoredLocalSourceDatabase
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _row_to_stored_local_source_database(
        row: dict[str, Any],
    ) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=row['name'],
            outdate_delay=row['outdate_delay'],
            outdate_action=row['outdate_action'],
            updated_at=row['updated_at'],
        )

    def load_stored_local_source_database(
        self, database_name: str
    ) -> StoredLocalSourceDatabase | None:
        self.execute(
            'SELECT * FROM `local_source_database` WHERE `name` = ?',
            (database_name,),
        )
        if row := self.fetchone():
            return self._row_to_stored_local_source_database(row)
        return None

    def update_stored_local_source_database(
        self, stored_database: StoredLocalSourceDatabase
    ):
        fields: list[str] = [
            'outdate_delay',
            'outdate_action',
            'updated_at',
        ]
        params: tuple = (
            stored_database.outdate_delay,
            stored_database.outdate_action,
            stored_database.updated_at,
        )
        field_sets = (f'`{f}` = ?' for f in fields)
        query = (
            f'UPDATE `local_source_database` '
            f'SET {", ".join(field_sets)} WHERE `name` = ?'
        )
        self.execute(query, params + (stored_database.name,))

    def insert_stored_local_source_database(
        self, stored_database: StoredLocalSourceDatabase
    ):
        fields: list[str] = [
            'name',
            'outdate_delay',
            'outdate_action',
            'updated_at',
        ]
        params: tuple = (
            stored_database.name,
            stored_database.outdate_delay,
            stored_database.outdate_action,
            stored_database.updated_at,
        )
        fields_str = ', '.join(f'`{field}`' for field in fields)
        self.execute(
            f'INSERT INTO `local_source_database` ({fields_str}) '
            f'VALUES ({", ".join("?" for _ in params)})',
            params,
        )

    # ---------------------------------------------------------------------------------
    # StoredPlayerCategorySet
    # ---------------------------------------------------------------------------------

    def _row_to_stored_player_category_set(
        self, row: dict[str, Any]
    ) -> StoredPlayerCategorySet:
        return StoredPlayerCategorySet(
            id=row['id'],
            name=row['name'],
            categories=self.load_json_from_database_field(row['categories']),
        )

    def load_player_category_sets(self) -> list[StoredPlayerCategorySet]:
        self.execute('SELECT * FROM `player_category_set`')
        return [self._row_to_stored_player_category_set(row) for row in self.fetchall()]

    def add_stored_player_category_set(
        self, stored_player_category_set: StoredPlayerCategorySet
    ) -> int:
        fields = {
            'name': stored_player_category_set.name,
            'categories': self.dump_to_json_database_field(
                stored_player_category_set.categories
            ),
        }
        fields_str = ', '.join(f'`{field}`' for field in fields)
        values_str = ', '.join(['?'] * len(fields))
        self.execute(
            f'INSERT INTO `player_category_set` ({fields_str}) VALUES ({values_str})',
            tuple(fields.values()),
        )
        id_ = self._last_inserted_id()
        if id_ is None:
            raise RuntimeError('Player category set insertion failed')
        return id_

    def delete_stored_player_category_set(self, player_category_set_id: int):
        self.execute(
            'DELETE FROM`player_category_set` WHERE `id` = ?',
            (player_category_set_id,),
        )
