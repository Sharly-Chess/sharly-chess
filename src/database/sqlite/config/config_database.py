from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import Any, Self, override, TYPE_CHECKING

from packaging.version import Version

from common import EVENTS_DIR
from common.exception import PapiWebException
from common.logger import get_logger
from database.sqlite.config import migrations
from database.sqlite.config.config_store import (
    StoredConfig,
    StoredPlugin,
    StoredLocalSourceDatabase,
)
from database.sqlite.migration_database import MigrationDatabase

if TYPE_CHECKING:
    from database.sqlite.migration import DatabaseMigrationManager

logger: Logger = get_logger()


class ConfigDatabase(MigrationDatabase):
    """The SQLite database class for Papi-web config."""

    # The file holding the configuration of the application.
    config_database_path: Path = EVENTS_DIR / '.scc'
    is_setup = False

    def __init__(self, write: bool = False):
        super().__init__(self.config_database_path, write)
        if not self.is_setup:
            self.__class__.is_setup = True
            self.setup()

    @classmethod
    @override
    def create_instance(cls, file: Path, write: bool = False) -> Self:
        return cls(write)

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

    @classmethod
    def setup(cls):
        """Setup the config database. If it does not exist, create it.
        If it is not up to date, update it."""
        database = cls()
        if not database.exists():
            database.create()
        else:
            try:
                with database:
                    status = database.check_status()
                if not status:
                    with cls(True) as write_database:
                        write_database.upgrade()
            except PapiWebException as e:
                logger.error(e)
                database.file.unlink(missing_ok=True)
                database.create()

    # ---------------------------------------------------------------------------------
    # StoredConfig
    # ---------------------------------------------------------------------------------

    def _row_to_stored_config(self, row: dict[str, Any]) -> StoredConfig:
        """Convert a row to a StoredConfig record."""
        return StoredConfig(
            force_edit=self.load_bool_from_database_field(row['force_edit']),
            log_level=row['log_level'],
            federation=row['federation'],
            launch_browser=self.load_bool_or_none_from_database_field(
                row['launch_browser']
            ),
            locale=row['locale'],
        )

    def _get_stored_config(self) -> StoredConfig:
        """Gets all the information about the config and returns a corresponding StoredConfig record."""
        self.execute(
            'SELECT * FROM `info`',
            (),
        )
        return self._row_to_stored_config(self.fetchone())

    def load_stored_config(self) -> StoredConfig:
        return self._get_stored_config()

    def update_stored_config(self, stored_config: StoredConfig) -> StoredConfig:
        """Updates the config database with the information in the provided `stored_config`."""
        fields: list[str] = [
            'force_edit',
            'log_level',
            'launch_browser',
            'federation',
            'locale',
        ]
        params: tuple = (
            stored_config.force_edit,
            stored_config.log_level,
            stored_config.launch_browser,
            stored_config.federation,
            stored_config.locale,
        )
        field_sets = (f'`{f}` = ?' for f in fields)
        self.execute(f'UPDATE `info` SET {", ".join(field_sets)}', tuple(params))
        return self._get_stored_config()

    # ---------------------------------------------------------------------------------
    # StoredPlugin
    # ---------------------------------------------------------------------------------

    def _row_to_stored_plugin(self, row: dict[str, Any]) -> StoredPlugin:
        return StoredPlugin(
            name=row['name'],
            is_enabled=self.load_bool_from_database_field(row['is_enabled']),
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
            'UPDATE `plugin` SET `is_enabled` = ? WHERE `name` = ?',
            (
                stored_plugin.is_enabled,
                stored_plugin.name,
            ),
        )
        return self.load_stored_plugin(stored_plugin.name)

    def insert_stored_plugin(self, stored_plugin: StoredPlugin):
        fields: list[str] = [
            'name',
            'is_enabled',
        ]
        params = (
            stored_plugin.name,
            stored_plugin.is_enabled,
        )
        fields_str = ', '.join(f'`{field}`' for field in fields)
        self.execute(
            f'INSERT INTO `plugin` ({fields_str}) '
            f'VALUES ({", ".join("?" for _ in params)})',
            params,
        )

    # ---------------------------------------------------------------------------------
    # StoredLocalSourceDatabase
    # ---------------------------------------------------------------------------------

    def _row_to_stored_local_source_database(
        self, row: dict[str, Any]
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
