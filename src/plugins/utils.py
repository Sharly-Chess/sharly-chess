from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, NamedTuple, override

from packaging.version import Version

from data.util import IdentifiableEntity
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredPlugin
from database.sqlite.migration import AbstractMigrationManager, AbstractMigration
from plugins import PLUGINS_DIR

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

    @staticmethod
    def insert_on_condition[T](
        source_list: list[T],
        element: T,
        condition: Callable[[T], bool],
        after: bool = True,
    ):
        """Inserts *element* into the list *source_list*. The insert in made at
        the position of the first element matching *condition*.
        If no element matches *condition*, append the element to the list.
        If *after* is True, element is inserted after the matched element,
        otherwise it is inserted before.
        """
        for index, match_element in enumerate(source_list):
            if condition(match_element):
                source_list.insert(index + after, element)
                return
        source_list.append(element)

    @classmethod
    def insert_on_equals[T](
        cls,
        source_list: list[T],
        element: T,
        match_element: T,
        after: bool = True,
    ):
        """Wrapper on insert_on_condition where the condition
        is an element being equal to *match_element*"""
        cls.insert_on_condition(
            source_list,
            element,
            lambda elem: elem == match_element,
            after
        )

    @classmethod
    def insert_on_isinstance[T](
        cls,
        source_list: list[T],
        element: T,
        insert_type: type[T],
        after: bool = True,
    ):
        """Wrapper on insert_on_condition where the condition
        is an element being an instance of *insert_type*"""
        cls.insert_on_condition(
            source_list,
            element,
            lambda elem: isinstance(elem, insert_type),
            after
        )


class PluginContext:
    def __init__(self, plugin: 'AbstractPlugin'):
        self.stored_plugin: StoredPlugin | None = None
        with ConfigDatabase() as database:
            self.stored_plugin = database.load_stored_plugin(plugin.id)
        if not self.stored_plugin:
            with ConfigDatabase(True) as database:
                self.stored_plugin = StoredPlugin(
                    name=plugin.id, is_enabled=plugin.default_is_enabled
                )
                database.insert_stored_plugin(self.stored_plugin)
                database.commit()


class AbstractPlugin(IdentifiableEntity, ABC):
    def __init__(self):
        self.context: PluginContext = PluginContext(self)

    @property
    @abstractmethod
    def description(self) -> str:
        """Briefly describes the features of the plugin."""
        pass

    @property
    @abstractmethod
    def version(self) -> Version:
        pass

    @cached_property
    def migration_manager(self) -> 'PluginMigrationManager | None':
        return None

    @property
    def default_is_enabled(self) -> bool:
        """Defines if the plugin is enabled by default."""
        return False

    @property
    def is_state_editable(self) -> bool:
        """Defines if the state of the plugin
        (enabled / disabled) is editable"""
        return True

    @property
    def is_enabled(self) -> bool:
        return self.context.stored_plugin.is_enabled

    @property
    def form_key(self) -> str:
        return f'plugin_{self.id}'

    @property
    def templates_path(self) -> Path:
        return PLUGINS_DIR / self.id / 'templates'

    @property
    def static_path(self) -> Path:
        return PLUGINS_DIR / self.id / 'static'

    def on_enable(self):
        """Method called when the plugin is enabled."""
        if self.migration_manager is not None:
            self._migrate_all_events()

    def on_disable(self):
        """Method called when the plugin is disabled."""
        if self.migration_manager is not None:
            self._migrate_all_events(
                PluginMigrationManager.EMPTY_DATABASE_VERSION
            )

    def _migrate_all_events(self, target_version: Version | None = None):
        """Migrates all the event databases to version *target_version*."""
        from data.loader import EventLoader
        from database.sqlite.event.event_database import EventDatabase

        for uniq_id in EventLoader().events_by_id:
            with EventDatabase(uniq_id, True, auto_upgrade=False) as database:
                self.migration_manager.migrate(database, target_version)

    def reload_context(self):
        self.context = PluginContext(self)

    def get_data(
        self,
        plugin_data: dict[str, dict] | None,
        field: str,
        default: Any = None,
    ) -> Any:
        return PluginUtils.get_plugin_data(self.id, plugin_data, field, default)


class PluginMigrationManager(AbstractMigrationManager):
    def __init__(
        self,
        plugin: AbstractPlugin,
        migration_module: ModuleType,
        cli_usage: bool = False,
    ):
        super().__init__(cli_usage)
        self._latest_version = plugin.version
        self.plugin_id = plugin.id
        self._migration_module = migration_module

    @property
    def base_module(self) -> ModuleType:
        return self._migration_module

    @override
    @property
    def latest_version(self) -> Version:
        return self._latest_version

    @override
    def get_version(self, database: 'EventDatabase') -> Version:
        return (
            database.get_plugin_version(self.plugin_id)
            or self.EMPTY_DATABASE_VERSION
        )

    @override
    def set_version(self, database: 'EventDatabase', version: Version):
        database.set_plugin_version(self.plugin_id, version)


class AbstractPluginMigration(AbstractMigration, ABC):
    @override
    @abstractmethod
    def backward(self):
        """As plugins are meant to be removable,
        all migrations need to be reversible."""
        pass


@dataclass
class PluginEngineArgument:
    flag: str
    name: str
    help: str
    engine_type: type['Engine']

    def init_engine(self) -> 'Engine':
        return self.engine_type()


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

