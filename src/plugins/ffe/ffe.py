
from plugins.hookspec import hookimpl, ExtraColumn
from data.util import PrintDocument

from common.i18n import _

#: Name of the plugin that will be referenced in our configuration
PLUGIN_NAME = "ffe"

@hookimpl
def get_extra_print_view_columns(document: PrintDocument):
    match document:
        case PrintDocument.PLAYER_LIST | PrintDocument.RANKINGS | PrintDocument.TOURNAMENT_SUMMARY:
            return [
                ExtraColumn(
                    insertion_index=4,
                    title=_('Cat *** CATEGORY FOR PRINT VIEW'),
                    classes="center",
                    value=lambda player: player.category.short_name,
                ),
                ExtraColumn(
                    insertion_index=5,
                    title=_('League *** LEAGUE FOR PRINT VIEW'),
                    classes="center",
                    value=lambda player: player.league,
                )
            ]
            
        case _:
            return
