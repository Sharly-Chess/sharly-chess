from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from packaging.version import Version

from data.player import Player
from database.sqlite.migration import AbstractMigrationManager

if TYPE_CHECKING:
    from common.engine import Engine
    from database.sqlite.event.event_database import EventDatabase


class PluginUtils:
    @staticmethod
    def get_plugin_data(
        plugin_id: str,
        plugin_data: dict[str, dict] | None,
        field: str,
        default: Any = None,
    ):
        return (plugin_data or {}).get(plugin_id, {}).get(field, default)


class AbstractPlugin(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> Version:
        pass

    def get_data(
        self,
        plugin_data: dict[str, dict] | None,
        field: str,
        default: Any = None,
    ) -> Any:
        return PluginUtils.get_plugin_data(self.id, plugin_data, field, default)


class AbstractPluginMigrationManager(AbstractMigrationManager, ABC):
    @property
    @abstractmethod
    def plugin(self) -> AbstractPlugin:
        pass

    def get_version(self, database: 'EventDatabase') -> Version:
        return (
            database.get_plugin_version(self.plugin.id)
            or self.EMPTY_DATABASE_VERSION
        )

    def set_version(self, database: 'EventDatabase', version: Version):
        database.set_plugin_version(self.plugin.id, version)


@dataclass
class PluginEngineArgument:
    flag: str
    name: str
    help: str
    engine_type: type['Engine']

    def init_engine(self) -> 'Engine':
        return self.engine_type()


@dataclass
class PrintSplitOption:
    name: str
    url_name: str
    split_fn: Callable[
        [list[Player]], dict[str, list[Player]]
    ]


@dataclass
class ExtraColumn:
    at: str
    title: str
    value: Callable[
        [Any], str
    ]
    classes: str = ""


class ExtraAdminColumn(NamedTuple):
    at: str
    header_template: str
    cell_template: str

