from abc import ABC, abstractmethod
from sqlite3 import OperationalError
from types import ModuleType
from typing import override

from packaging.version import Version

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.migration import BaseMigration, MigrationManager
from plugins.utils import AbstractPlugin


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
        database: EventDatabase,
        base_migration_module: ModuleType,
        plugin: AbstractPlugin,
    ):
        super().__init__(database, base_migration_module)
        self.plugin = plugin

    def get_migration(self) -> str:
        return self.database.get_plugin_migration(self.plugin.id)

    def set_migration(self, migration: str):
        self.database.set_plugin_migration(self.plugin.id, migration)

    def get_version(self) -> Version:
        return self.database.get_plugin_version(self.plugin.id)

    def set_version(self, version: Version):
        self.database.set_plugin_version(self.plugin.id, version)

    @property
    def latest_version(self) -> Version:
        return self.plugin.version

    @property
    def is_metadata_installed(self) -> bool:
        try:
            return self.database.is_plugin_in_metadata_table(self.plugin.id)
        except OperationalError:
            return False

    def install_metadata(self):
        self.database.create_plugin_metadata_table()
        self.database.insert_plugin_metadata(
            self.plugin.id, self.plugin.version
        )

    @override
    @property
    def log_prefix(self) -> str:
        return (
            f'Database [{self.database.file.name}] - '
            f'Plugin [{self.plugin.name}] - '
        )

    def get_migration_from_legacy_version(self) -> str | None:
        try:
            self.database.execute(
                f'SELECT `{self._legacy_version_field}` FROM `info`'
            )
        except OperationalError:
            return None
        return 'm001_retrieve_deprecated_plugin_columns'

    def remove_legacy_version_field(self):
        try:
            self.database.execute(
                f'ALTER TABLE `info` DROP COLUMN `{self._legacy_version_field}`'
            )
        except OperationalError:
            pass

    @property
    def _legacy_version_field(self) -> str:
        return f'{self.plugin.id}_plugin_version'
