from abc import ABC, abstractmethod
from sqlite3 import OperationalError
from types import ModuleType
from typing import override

from packaging.version import Version

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.migration import BaseMigration, MigrationManager
from plugins.utils import Plugin


class BasePluginMigration(BaseMigration, ABC):
    """Base class for all plugin migrations."""

    @override
    @abstractmethod
    def backward(self):
        """As plugins are meant to be removable,
        all migrations need to be reversible."""


class PluginMigrationManager(MigrationManager[EventDatabase]):
    """Migration manager for plugins to apply to the event databases."""

    def __init__(
        self,
        base_database: EventDatabase,
        base_migration_module: ModuleType,
        plugin: Plugin,
    ):
        super().__init__(base_database, base_migration_module)
        self.plugin = plugin

    def get_migration(self, database: EventDatabase) -> str:
        return database.get_plugin_migration(self.plugin.id)

    def set_migration(self, migration: str, database: EventDatabase):
        database.set_plugin_migration(self.plugin.id, migration)

    def get_version(self, database: EventDatabase) -> Version:
        return database.get_plugin_version(self.plugin.id)

    def set_version(self, version: Version, database: EventDatabase):
        database.set_plugin_version(self.plugin.id, version)

    @property
    def latest_version(self) -> Version:
        return self.plugin.version

    def is_metadata_installed(self, database: EventDatabase) -> bool:
        try:
            return database.is_plugin_in_metadata_table(self.plugin.id)
        except OperationalError:
            return False

    def install_metadata(self, database: EventDatabase):
        database.create_plugin_metadata_table()
        database.insert_plugin_metadata(self.plugin.id, self.plugin.version)

    @property
    def log_prefix(self) -> str:
        return super().log_prefix + f'Plugin [{self.plugin.id}] - '

    def get_migration_from_legacy_version(self, database: EventDatabase) -> str | None:
        try:
            database.execute(f'SELECT `{self._legacy_version_field}` FROM `info`')
        except OperationalError:
            return None
        return 'm001_retrieve_deprecated_plugin_columns'

    def remove_legacy_version_field(self, database: EventDatabase):
        try:
            database.execute(
                f'ALTER TABLE `info` DROP COLUMN `{self._legacy_version_field}`'
            )
        except OperationalError:
            pass

    @property
    def _legacy_version_field(self) -> str:
        return f'{self.plugin.id}_plugin_version'
