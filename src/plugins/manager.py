from functools import cached_property
from pathlib import Path

from pluggy import PluginManager  # type: ignore

from common import APP_NAME
from plugins.hookspec import AppHookSpecs
from plugins.utils import Plugin


class AppPluginManager(PluginManager):
    """
    Our own custom subclass of PluginManager. We do this to add several convenience methods
    we use elsewhere in our application.
    """

    @cached_property
    def all_plugins(self) -> list[Plugin]:
        from plugins.chessevent.chessevent import ChessEventPlugin
        from plugins.ffe.ffe import FfePlugin

        return [
            FfePlugin(),
            ChessEventPlugin(),
        ]

    @property
    def enabled_plugins(self) -> list[Plugin]:
        return [plugin for plugin in self.all_plugins if plugin.is_enabled]

    @property
    def templates_paths(self) -> list[Path]:
        """Template paths of all plugins (even disabled ones)
        need to be added to the jinja engine."""
        return [
            plugin.templates_path
            for plugin in self.all_plugins
            if plugin.templates_path.exists()
        ]

    @property
    def static_paths(self) -> list[Path]:
        """Static paths of all plugins (even disabled ones)
        need to be added to the jinja engine."""
        return [
            plugin.static_path
            for plugin in self.all_plugins
            if plugin.static_path.exists()
        ]

    def load_register(self):
        for plugin in self.enabled_plugins:
            self.register(plugin, plugin.id)

    def reload_register(self):
        for plugin in self.all_plugins:
            was_enabled = plugin.is_enabled
            plugin.reload_context()
            is_enabled = plugin.is_enabled
            if is_enabled and not was_enabled:
                plugin.on_enable()
                self.register(plugin, plugin.id)
            elif not is_enabled and was_enabled:
                plugin.on_disable()
                self.unregister(plugin, plugin.id)


plugin_manager = AppPluginManager(APP_NAME)
plugin_manager.add_hookspecs(AppHookSpecs)
plugin_manager.load_register()
