from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.version import Version

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.migration import AbstractMigrationManager

if TYPE_CHECKING:
    from common.engine import Engine


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


@dataclass
class PluginEngineArgument:
    flag: str
    name: str
    help: str
    engine_type: type['Engine']

    def init_engine(self) -> 'Engine':
        return self.engine_type()
