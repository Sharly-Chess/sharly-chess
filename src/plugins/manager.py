from functools import cached_property
from pathlib import Path
from typing import Any, Type, TypeVar, TYPE_CHECKING, Optional

from apluggy import PluginManager  # type: ignore

from common import APP_NAME
from plugins.hookspec import AppHookSpecs
from plugins.utils import Plugin

if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import StoredEvent

TPlugin = TypeVar('TPlugin', bound=Plugin[Any])


class AppPluginManager(PluginManager):
    """
    Our own custom subclass of PluginManager. We do this to add several convenience methods
    we use elsewhere in our application.
    """

    @cached_property
    def all_plugins(self) -> list[Plugin]:
        from plugins.chess_results.chess_results import ChessResultsPlugin
        from plugins.chessevent.chessevent import ChessEventPlugin
        from plugins.ffe.ffe import FfePlugin
        from plugins.pairing_acceleration.pairing_acceleration import (
            PairingAccelerationPlugin,
        )

        return [
            PairingAccelerationPlugin(),
            ChessResultsPlugin(),
            FfePlugin(),
            ChessEventPlugin(),
        ]

    def get_plugin_by_class(self, plugin_cls: Type[TPlugin]) -> TPlugin:
        for plugin in self.all_plugins:
            if isinstance(plugin, plugin_cls):
                return plugin
        raise ValueError(f'Plugin {plugin_cls.__name__} not found')

    @property
    def default_plugins_with_dependencies(self) -> list[Plugin]:
        default_plugins = [
            plugin for plugin in self.all_plugins if plugin.is_default_enabled
        ]
        return self.get_plugins_with_dependencies(default_plugins)

    def get_plugins_with_dependencies(self, plugins: list[Plugin]) -> list[Plugin]:
        plugins_with_dependencies: list[Plugin] = []
        while plugins:
            plugin = plugins.pop()
            if plugin in plugins_with_dependencies:
                continue
            plugins_with_dependencies.append(plugin)
            for dependency_type in plugin.dependencies:
                dependency = self.get_plugin_by_class(dependency_type)
                if dependency not in plugins_with_dependencies:
                    plugins.append(dependency)
        return plugins_with_dependencies

    def get_event_enablable_plugins(self, stored_event: 'StoredEvent') -> list[Plugin]:
        return [
            plugin
            for plugin in self.all_plugins
            if plugin.can_be_enabled_for_event(stored_event)
        ]

    @property
    def templates_paths(self) -> list[Path]:
        return [
            plugin.templates_path
            for plugin in self.all_plugins
            if plugin.templates_path.exists()
        ]

    @property
    def static_paths(self) -> list[Path]:
        return [
            plugin.static_path
            for plugin in self.all_plugins
            if plugin.static_path.exists()
        ]

    def load_register(self):
        for plugin in self.all_plugins:
            self.register(plugin, plugin.id)

    def hook_for_event(self, event: Optional['Event'], hook_name: str):
        return self.subset_hook_caller(
            hook_name, remove_plugins=event.disabled_plugins if event else []
        )

    def hook_for_default_plugins(self, hook_name: str):
        default_plugins = self.default_plugins_with_dependencies
        return self.subset_hook_caller(
            hook_name,
            remove_plugins=[
                plugin for plugin in self.all_plugins if plugin not in default_plugins
            ],
        )


_plugin_manager = None


def get_plugin_manager() -> AppPluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = AppPluginManager(APP_NAME)
        _plugin_manager.add_hookspecs(AppHookSpecs)
        _plugin_manager.load_register()
    return _plugin_manager


# Create a lazy proxy object
# This is to avoid circular imports
class LazyPluginManager:
    def __getattr__(self, name):
        return getattr(get_plugin_manager(), name)


plugin_manager: AppPluginManager = LazyPluginManager()  # type: ignore[assignment]
