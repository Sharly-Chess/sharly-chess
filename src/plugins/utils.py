from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, NamedTuple, Self, Optional

from packaging.version import Version

from utils.entity import IdentifiableEntity
from plugins import PLUGINS_DIR

if TYPE_CHECKING:
    from database.sqlite.event.event_database import EventDatabase
    from plugins.migration import PluginMigrationManager
    from web.controllers.base_controller import BaseController
    from data.event import Event


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
            source_list, element, lambda elem: elem == match_element, after
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
            source_list, element, lambda elem: isinstance(elem, insert_type), after
        )


class PluginContext:
    def __init__(self, plugin: 'Plugin'):
        from database.sqlite.config.config_database import ConfigDatabase
        from database.sqlite.config.config_store import StoredPlugin

        self.stored_plugin: StoredPlugin
        with ConfigDatabase() as database:
            stored_plugin = database.load_stored_plugin(plugin.id)
        if not stored_plugin:
            with ConfigDatabase(True) as database:
                stored_plugin = StoredPlugin(
                    name=plugin.id, is_enabled=plugin.default_is_enabled
                )
                database.insert_stored_plugin(stored_plugin)
        self.stored_plugin = stored_plugin

    def get_raw_plugin_data(self) -> dict[str, Any]:
        return self.stored_plugin.plugin_data or {}


class PluginData(ABC):
    @classmethod
    @abstractmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        """Initialize an object from its stored value."""

    @abstractmethod
    def to_stored_value(self) -> dict[str, Any]:
        """The value to store in the database."""

    @classmethod
    @abstractmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        """Initialize an object from form data."""

    @abstractmethod
    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        """The values to use in a form."""


class Plugin[PD: PluginData](IdentifiableEntity, ABC):
    data_class: type[PD] | None = None

    def __init__(self):
        self.context: PluginContext = PluginContext(self)

    @property
    @abstractmethod
    def description(self) -> str:
        """Briefly describes the features of the plugin."""

    @property
    @abstractmethod
    def version(self) -> Version:
        """Version of the plugin."""

    @cached_property
    def base_migration_module(self) -> ModuleType | None:
        """Module containing the migration timeline of the module.
        None if the plugin does not have migrations."""
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
    def federation(self) -> str | None:
        """Returns the federation for which the plugin is enabled,, or None for all"""
        return None

    @property
    def is_enabled(self) -> bool:
        assert self.context.stored_plugin is not None
        return self.context.stored_plugin.is_enabled

    def is_enabled_for_event(self, event: Optional['Event']) -> bool:
        """Determines if the plugin is enabled for the given event"""
        return True

    @property
    def form_key(self) -> str:
        return f'plugin_{self.id}'

    @property
    def templates_path(self) -> Path:
        return PLUGINS_DIR / self.id / 'templates'

    @property
    def static_path(self) -> Path:
        return PLUGINS_DIR / self.id / 'static'

    @property
    def controllers(self) -> list[type['BaseController']]:
        """List of controllers for the plugin. Has to be passed this way instead
        of a hook as controllers are initialized at the start of the application."""
        return []

    def get_plugin_data(self) -> PD:
        raw_data = self.context.get_raw_plugin_data()
        if self.data_class is None:
            raise NotImplementedError(
                f'{self.__class__.__name__} must define data_class'
            )
        return self.data_class.from_stored_value(raw_data)

    def get_migration_manager(
        self, database: 'EventDatabase'
    ) -> 'PluginMigrationManager':
        from plugins.migration import PluginMigrationManager

        assert self.base_migration_module is not None
        return PluginMigrationManager(database, self.base_migration_module, self)

    def on_enable(self):
        """Method called when the plugin is enabled."""
        if self.base_migration_module is not None:
            self._migrate_all_events()

    def _migrate_all_events(self, target_migration: str | None = None):
        """Migrates all the event databases to migration."""
        from data.loader import EventLoader
        from database.sqlite.event.event_database import EventDatabase

        for uniq_id in EventLoader().event_uniq_ids:
            database = EventDatabase(uniq_id)
            if migration_manager := self.get_migration_manager(database):
                migration_manager.migrate(target_migration)

    def reload_context(self):
        self.context = PluginContext(self)

    def get_data(
        self,
        plugin_data: dict[str, dict] | None,
        field: str,
        default: Any = None,
    ) -> Any:
        return PluginUtils.get_plugin_data(self.id, plugin_data, field, default)


@dataclass
class ExtraColumn:
    at: str
    title: str
    value: Callable[[Any], str]
    classes: str = ''


class ExtraAdminColumn(NamedTuple):
    at: str
    header_template: str
    cell_template: str


class ExtraStatisticsSection(NamedTuple):
    at: str
    title: str
    rows: dict[str, int]
    subtitle: str | None


class NavUploadItem(NamedTuple):
    """Class representing an upload item in the navigation bar."""

    key: str
    title: str
    icon_path: str
    modal_route_name: str
    has_upload_error: bool
