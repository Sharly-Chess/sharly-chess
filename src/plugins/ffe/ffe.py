
from common import BASE_DIR
from data.player import Player
from database.sqlite.ffe_database import FfeDatabase
from plugins.hookspec import hookimpl, ExtraColumn
from data.util import PlayerRatingType, PrintDocument, TournamentRating

from common.i18n import _

from .ffe_search_controller import FfeSearchController

#: Name of the plugin that will be referenced in our configuration
PLUGIN_NAME = "ffe"

@hookimpl
def get_controllers():
    return [
        FfeSearchController,
    ]

@hookimpl
def get_templates_path():
    return BASE_DIR / 'src/plugins/ffe/templates'

@hookimpl
def get_player_search_template():
    return "/ffe_search.html"

@hookimpl
def augment_player(player: Player):
    # Try to get more information by requesting the FFE database
    if FfeDatabase().exists():
        with FfeDatabase() as ffe_database:
            if ffe_player := ffe_database.get_player_by_fide_id(player.fide_id):
                player.ffe_id = ffe_player.ffe_id
                for rating_type in [
                    TournamentRating.STANDARD,
                    TournamentRating.RAPID,
                    TournamentRating.BLITZ,
                ]:
                    if player.rating_types[rating_type] == PlayerRatingType.ESTIMATED:
                        player.ratings[rating_type] = ffe_player.ratings[rating_type]
                        player.rating_types[rating_type] = ffe_player.rating_types[rating_type]
                if ffe_player.date_of_birth and player.year_of_birth == ffe_player.year_of_birth:
                    player.date_of_birth = ffe_player.date_of_birth
                player.ffe_licence = ffe_player.ffe_licence
                player.ffe_licence_number = ffe_player.ffe_licence_number
                player.club = ffe_player.club
                player.league = ffe_player.league
                player.comment = ffe_player.comment
    
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
