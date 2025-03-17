from collections.abc import Iterable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Any, TYPE_CHECKING

from litestar.contrib.htmx.request import HTMXRequest
import pluggy  # type: ignore

from common import APP_NAME
from data.player import Player
from data.tournament_export import AbstractTournamentExporter
from data.util import PrintDocument, ScreenType
from plugins.utils import AbstractPluginMigrationManager, PluginEngineArgument

if TYPE_CHECKING:
    from data.tie_break import AbstractTieBreak
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredEvent
    from database.sqlite.event.event_store import StoredTournament
    from plugins.utils import AbstractPluginMigrationManager, PluginEngineArgument
    from web.controllers.base_controller import BaseController
    from web.controllers.admin.player_admin_controller import PlayerAdminWebContext

hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)

@dataclass
class PrintSplitOption:
    name: str
    url_name: str
    split_fn: Callable[
        [list[Player]], dict[str, list[Player]]
    ]


@dataclass
class ExtraColumn:
    at: str
    title: str
    value: Callable[
        [Any], str
    ]
    classes: str = ""


class ExtraAdminColumn(NamedTuple):
    at: str
    header_template: str
    cell_template: str


class AppHookSpecs:
    """Holds all hookspecs for this application"""
    
    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @hookspec
    def on_init(self):
        """Provide any initialisation""" 

    @hookspec
    def get_event_migration_manager(self) -> AbstractPluginMigrationManager:
        """Provide a migration manager for event databases"""
        
    @hookspec
    def get_controllers(self) -> Iterable[type['BaseController']]:
        """Provide controllers for the application"""

    @hookspec
    def get_templates_path(self) -> Path:
        """Provide base path to any provided templates"""

    @hookspec
    def get_base_admin_template_context(self) -> dict[str, Any]:
        """Provide additional template context for AdminWebContext"""

    @hookspec
    def get_engine_argument(self) -> PluginEngineArgument:
        """Provide an engine argument"""
        
    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------
    
    @hookspec
    def get_db_player_fields(self) -> list[str]:
        """Provide addition column field names to read from the database"""

    @hookspec
    def augment_player_after_db_fetch(
        self, player: Player, row: dict[str, Any]
    ) -> list[str]:
        """Add plugin specific data to a player after they are fetched from the database"""

    @hookspec
    def player_data_for_db_write(self, player: Player) -> dict[str, Any]:
        """Provide addition column data for players when writing to the database"""
                
    @hookspec
    def get_player_admin_template_context(self, web_context: 'PlayerAdminWebContext') -> dict[str, Any]:
        """Provide additional template context for rendering in PlayerAdminController"""

    @hookspec
    def get_player_search_template(self) -> str:
        """Provide a path to a player search template"""

    @hookspec
    def get_player_form_fields_template(self) -> str:
        """Provide a path to a template containing additional player form fields"""

    @hookspec
    def get_player_form_data(
        self, plugin_data: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Provide form data for the additional player form fields"""

    @hookspec
    def get_validated_player_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str]
    ) -> dict[str, Any]:
        """Validate the additional player form fields and returns plugin data"""
        
    @hookspec
    def augment_player_after_search(self, player: Player):
        """Add plugin specific data to a player after a a successful player search"""

    @hookspec
    def set_player_default_ratings(self, federation: str, player: 'Player'):
        """Set default ratings for an unrated player when they are added to an event"""

    @hookspec(firstresult=True)
    def is_tournament_participation_possible(
        self, tournament: 'Tournament', player: Player
    ) -> str | None:
        """Test if a player can participate in a tournament"""

    @hookspec
    def get_extra_player_columns(self) -> Iterable[ExtraAdminColumn]:
        """Provide additional columns for the player table view"""
        
    @hookspec
    def filter_player(self, web_context: 'PlayerAdminWebContext', template_context: dict[str, Any], player: Player) -> bool:
        """Returns True if the player should be in the admin player list, False otherwise """

    @hookspec
    def clear_player_filters(self, request: HTMXRequest):
        """Clear any filters set on the admin players tab"""

    @hookspec(firstresult=True)
    def player_club_sort_key(self, player: Player) -> tuple:
        """Returns a sort key for sorting the admin player list by club """
        
    @hookspec
    def get_extra_players_datasheet_columns(self) -> Iterable[ExtraColumn]:
        """Provide extra columns for the player download datasheets """
        
    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookspec
    def augment_event_after_db_fetch(self, stored_event: 'StoredEvent', row: dict[str, Any]):
        """Add plugin specific data to the StoredEvent after all columns are fetched from the database"""
        
    @hookspec
    def event_data_for_db_write(self, stored_event: 'StoredEvent') -> dict[str, Any]:
        """Provide addition column data for events when writing to the database"""
        
    @hookspec
    def get_event_info_rows_template(self) -> str:
        """Provide a path to the template containing extra event info rows"""

    @hookspec
    def get_event_card_block_template(self) -> str:
        """Provide a path to the template to be added to event cards"""

    @hookspec
    def get_event_form_fields_template(self) -> str:
        """Returns the path of the template for additional fields of the event modal"""
      
    @hookimpl
    def get_event_form_data(self, event: 'Event | None') -> dict[str, Any]:
        """Provide form data for the additional event form fields"""
    
    @hookimpl
    def get_validated_event_form_fields(self, action: str, event: 'Event | None', data: dict[str, str], errors: dict[str, str]) -> dict[str, Any]:
        """Validate the additional event form fields and return as plugin data"""
        
    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------  

    @hookspec
    def augment_tournament_after_db_fetch(self, stored_tournament: 'StoredTournament', row: dict[str, Any]):
        """Add plugin specific data to a StoredTournament after all columns are fetched from the database"""


    @hookspec
    def tournament_data_for_db_write(self, stored_tournament: 'StoredTournament') -> dict[str, Any]:
        """Provide addition column data for tournaments when writing to the database"""
          
    @hookspec
    def on_tournament_init(self, tournament: 'Tournament'):
        """Do any tournament specific initialisation when a Tournament object is initialised"""
             
    @hookspec
    def get_tournament_form_fields_template(self) -> str:
        """Provide a path to the template containing additional tournament form fields"""
        
    @hookspec
    def get_tournament_form_data(
        self, tournament: 'Tournament | None',
    ) -> dict[str, Any]:
        """Provide form data for the additional tournament form fields"""

    @hookspec
    def get_validated_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str]
    ) -> dict[str, Any]:
        """Validate the additional tournament form fields and return as plugin data"""

    @hookspec
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        """Provide a path to the template to be added to tournament cards"""

    @hookspec
    def get_extra_tournament_exporters(self) -> list[AbstractTournamentExporter]:
        """Provide extra exporting formats for tournaments"""
        
    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------  

    @hookspec
    def get_print_split_options(self) -> Iterable[PrintSplitOption]:
        """Provide print splitting options"""

    @hookspec
    def split_printed_players_by(self, split_by: str, players: list[Player]):
        """Split players by the chosen split option"""

    @hookspec
    def get_extra_print_view_columns(self, document: PrintDocument) -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    # ---------------------------------------------------------------------------------
    # User screens
    # ---------------------------------------------------------------------------------  
    
    @hookspec
    def get_extra_screen_columns(self, screen: ScreenType) -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    # ---------------------------------------------------------------------------------
    # Tie breaks
    # ---------------------------------------------------------------------------------  

    @hookspec
    def get_extra_tie_break_classes(self) -> list[type['AbstractTieBreak']]:
        """Provide extra tournament tie breaks"""
