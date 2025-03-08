from pluggy import PluginManager  # type: ignore

from common import APP_NAME
from plugins.hookspec import AppHookSpecs
from plugins.ffe import ffe
from plugins.chessevent import chessevent
class AppPluginManager(PluginManager):
    """
    Our own custom subclass of PluginManager. We do this to add several convenience methods
    we use elsewhere in our application.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

plugin_manager = AppPluginManager(APP_NAME)
plugin_manager.add_hookspecs(AppHookSpecs)

# Registers internal plugin hooks
plugin_manager.register(chessevent)
plugin_manager.register(ffe)
