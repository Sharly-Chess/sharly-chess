from plugins.manager import plugin_manager
from plugins.ffe import ffe
from plugins.chessevent import chessevent

def register_plugins():
    plugin_manager.register(chessevent)
    plugin_manager.register(ffe)
