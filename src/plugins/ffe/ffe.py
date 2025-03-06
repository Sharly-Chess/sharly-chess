
from plugins.hookspec import hookimpl

#: Name of the plugin that will be referenced in our configuration
PLUGIN_NAME = "ffe"

@hookimpl
def test():
    return "ffe"
