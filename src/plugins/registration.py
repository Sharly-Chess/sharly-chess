from plugins.manager import plugin_manager
from plugins.ffe.ffe import FfePlugin
from plugins.chessevent.chessevent import ChessEventPlugin


def register_plugins():
    plugin_manager.register(ChessEventPlugin())
    plugin_manager.register(FfePlugin())
