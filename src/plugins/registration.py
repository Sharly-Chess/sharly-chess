import plugins.manager as PM

from plugins.ffe import ffe
from plugins.chessevent import chessevent

def register_plugins():
    PM.plugin_manager.register(chessevent)
    PM.plugin_manager.register(ffe)
