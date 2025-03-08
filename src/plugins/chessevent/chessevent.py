
from common import BASE_DIR
from plugins.hookspec import hookimpl

#: Name of the plugin that will be referenced in our configuration
PLUGIN_NAME = "chessevent"

@hookimpl
def get_templates_path():
    return BASE_DIR / 'src/plugins/chessevent/templates'

@hookimpl
def get_tournament_card_block_template():
    return "/chessevent_tournament_card_block.html"
