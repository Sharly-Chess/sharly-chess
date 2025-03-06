
from collections import defaultdict
from functools import partial

from common import BASE_DIR
from data.player import Player
from data.util import PlayerCategory, PlayerRatingType, PrintDocument, TournamentRating
from database.sqlite.ffe_database import FfeDatabase
from plugins.hookspec import PrintSplitOption, hookimpl, ExtraColumn

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
def get_tournament_card_block_template():
    return "/ffe_tournament_card_block.html"

def split_players_by(split_by: str, players: list[Player]):
    split_functions = {
        "ffe-category": lambda p: p.category.short_name,
        "ffe-league": lambda p: p.league_tuple.league,
    } 
    
    if split_by == "ffe-category":
        split_players = {
            category.short_name: [] for category in PlayerCategory
        }
    else:
        split_players = defaultdict(list)

    # Split players by group
    for player in players:
        split_players[split_functions[split_by](player)].append(player)

    if split_by == "ffe-category":
        # Filter out empty categories
        split_players = {
            key: split_players[key] for key in split_players.keys()
            if len(split_players[key]) > 0
        }
    else:
        # Sort by key
        split_players = {
            key: split_players[key]
            for key in sorted(split_players.keys())
        }
    return split_players
    
@hookimpl
def get_print_split_options():
    return [
        PrintSplitOption(
            name=_('Category'),
            url_name="ffe-category",
            split_fn=partial(split_players_by, "ffe-category"),
        ),
        PrintSplitOption(
            name=_('League'),
            url_name="ffe-league",
            split_fn=partial(split_players_by, "ffe-league"),
        ),
    ]

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
