from abc import ABC, abstractmethod

from packaging.version import Version

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.migration import AbstractMigrationManager


class AbstractPluginMigrationManager(AbstractMigrationManager, ABC):
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def latest_plugin_version(self) -> Version:
        pass

    def get_version(self, database: EventDatabase) -> Version:
        return (
            database.get_plugin_version(self.plugin_name)
            or self.EMPTY_DATABASE_VERSION
        )

    def set_version(self, database: EventDatabase, version: Version):
        database.set_plugin_version(self.plugin_name, version)
