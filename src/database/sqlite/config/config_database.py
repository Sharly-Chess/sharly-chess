from logging import Logger
from pathlib import Path
from types import ModuleType
from typing import Any, Self

from packaging.version import Version

from common import PAPI_WEB_VERSION
from common.logger import get_logger
from database.sqlite.config import migrations
from database.sqlite.config.config_store import StoredConfig, StoredPlugin, StoredLocalSourceDatabase
from database.sqlite.migration import AbstractMigrationManager
from database.sqlite.versioned_database import SQLiteVersionedDatabase

logger: Logger = get_logger()


class ConfigMigrationManager(AbstractMigrationManager):
    @property
    def base_module(self) -> ModuleType:
        return migrations


class ConfigDatabase(SQLiteVersionedDatabase):
    """
    The SQLite database class for Papi-web config.
    """

    # The file holding the configuration of the application.
    config_database_path: Path = Path('.scc')

    def __init__(self, write: bool = False, auto_upgrade: bool = True):
        super().__init__(self.config_database_path, write, auto_upgrade)
        if not self.exists():
            self.create()

    @classmethod
    def from_parent(cls, parent: SQLiteVersionedDatabase) -> Self:
        return cls(parent.write, parent.auto_upgrade)

    @property
    def stored_version(self) -> Version:
        return Version(self._get_stored_config().version)

    def set_version(self, version: Version):
        """Sets the version field stored in the database to `version`."""
        self.execute(
            'UPDATE `info` SET `version` = ?',
            (f'{version.major}.{version.minor}.{version.micro}', ),
        )
        self._version = version

    @property
    def migration_manager(self) -> AbstractMigrationManager:
        return ConfigMigrationManager()

    def insert_creation_values(self):
        version = PAPI_WEB_VERSION
        self.execute(
            "INSERT INTO `info`(`version`, `force_edit`) VALUES(?, ?)",
            (f'{version.major}.{version.minor}.{version.micro}', True)
        )

    # ---------------------------------------------------------------------------------
    # StoredConfig
    # ---------------------------------------------------------------------------------

    def _row_to_stored_config(self, row: dict[str, Any]) -> StoredConfig:
        """Convert a row to a StoredConfig record."""
        return StoredConfig(
            version=row['version'],
            force_edit=self.load_bool_from_database_field(row['force_edit']),
            log_level=row['log_level'],
            federation=row['federation'],
            launch_browser=self.load_bool_from_database_field(row['launch_browser']),
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
            False,
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

    def update_stored_plugin(
        self, stored_plugin: StoredPlugin
    ) -> StoredPlugin | None:
        self.execute(
            'UPDATE `plugin` SET `is_enabled` = ? WHERE `name` = ?',
            (stored_plugin.is_enabled, stored_plugin.name,),
        )
        return self.load_stored_plugin(stored_plugin.name)

    def insert_stored_plugin(self, stored_plugin: StoredPlugin) -> StoredPlugin:
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
            f'VALUES ({', '.join('?' for _ in params)})',
            params,
        )
        return self.load_stored_plugin(stored_plugin.name)

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

    def update_stored_local_source_database(
            self, stored_database: StoredLocalSourceDatabase
    ) -> StoredPlugin | None:
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
            f'SET {', '.join(field_sets)} WHERE `name` = ?'
        )
        self.execute(query, params + (stored_database.name,))
        return self.load_stored_local_source_database(
            stored_database.name
        )

    def insert_stored_local_source_database(
        self, stored_database: StoredLocalSourceDatabase
    ) -> StoredLocalSourceDatabase:
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
            f'VALUES ({', '.join('?' for _ in params)})',
            params,
        )
        return self.load_stored_local_source_database(
            stored_database.name
        )
