
from common import BASE_DIR
from data.player import Player
from database.sqlite.ffe_database import FfeDatabase
from plugins.hookspec import hookimpl, ExtraColumn
from data.util import PlayerRatingType, PrintDocument, TournamentRating

from common.i18n import _

#: Name of the plugin that will be referenced in our configuration
PLUGIN_NAME = "chess_event"

@hookimpl
def get_templates_path():
    return BASE_DIR / 'src/plugins/chess_event/templates'

@hookimpl
def get_tournament_card_block_template():
    return "/chess_event_tournament_card_block.html"
