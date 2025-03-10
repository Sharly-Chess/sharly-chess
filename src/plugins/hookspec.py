from pathlib import Path
import pluggy  # type: ignore
from typing import NamedTuple, Any, TYPE_CHECKING
from collections.abc import Iterable, Callable
from data.player import Player
from common import APP_NAME
from data.tournament_export import AbstractTournamentExporter
from data.util import PrintDocument, ScreenType

if TYPE_CHECKING:
    from data.tournament import Tournament
    from web.controllers.base_controller import BaseController
    
hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)

class PrintSplitOption(NamedTuple):
    name: str
    url_name: str
    split_fn: Callable[
        [list[Player]], dict[str, list[Player]]
    ]

class ExtraColumn(NamedTuple):
    at: str
    title: str
    classes: str
    value: Callable[
        [Any], str
    ]

class ExtraAdminColumn(NamedTuple):
    at: str
    header_template: str
    cell_template: str
class AppHookSpecs:
    """Holds all hookspecs for this application"""

    @hookspec
    def on_init(self) -> Iterable[Iterable['BaseController']]:
        """Provide any initialisation"""

    @hookspec
    def get_controllers(self) -> Iterable[Iterable['BaseController']]:
        """Provide controllers for the application"""
        
    @hookspec
    def get_templates_path(self) -> Iterable[Iterable[Path]]:
        """Provide base path to any provided templates"""
        
    @hookspec
    def get_base_admin_context(self) -> Iterable[dict[str, Any]]:
        """Provide plugin context for the AdminWebContext"""
        
    @hookspec
    def get_player_search_template(self) -> Iterable[str]:
        """Provide a path to the player search template"""

    @hookspec
    def get_player_form_fields_template(self) -> Iterable[str]:
        """Provide a path to the template containing player form fields"""
    
    @hookspec
    def get_player_form_data(self, plugin_data: dict[str, dict[str, Any]]) -> Iterable[dict[str, Any]]:
        """Provide form data for the player form fields"""
    
    @hookspec
    def get_validated_player_form_fields(self, action: str, tournament: 'Tournament', data: dict[str, str], errors: dict[str, str]) -> Iterable[dict[str, Any]]:
        """Validate player form fields"""
        
    @hookspec
    def get_db_player_fields(self) -> Iterable[list[str]]:
        """Provide extra fields to read or write to the player database"""
        
    @hookspec
    def augment_player_after_db_fetch(self, player: Player, row: dict[str: Any]) -> Iterable[list[str]]:
        """Add plugin specific data to a player after they are fetched from the database"""
    
    @hookspec
    def player_data_for_db_write(self, player: Player) -> Iterable[dict[str: Any]]:
        """Provide data for player fields to write to the database"""
        
    @hookspec
    def augment_player_after_search(self, player: Player):
        """Add plugin specific data to a player"""
    
    @hookspec(firstresult=True)
    def is_tournament_participation_possible(self, tournament: 'Tournament', player: Player) -> Iterable[str]:
        """Test if a play can participate in a tournament"""
    
    @hookspec
    def get_tournament_card_block_template(self) -> Iterable[str]:
        """Provide a path to the template to be added to tournament cards"""
    
    @hookspec
    def get_print_split_options(self) -> Iterable[Iterable[PrintSplitOption] | None]:
        """Provide print splitting options"""

    @hookspec
    def get_extra_player_columns(self) -> Iterable[Iterable[ExtraAdminColumn] | None]:
        """Provide extra columns for the print view"""
        
    @hookspec
    def get_extra_print_view_columns(self, document: PrintDocument) -> Iterable[Iterable[ExtraColumn] | None]:
        """Provide extra columns for the print view"""
    
    @hookspec
    def get_extra_screen_columns(self, screen: ScreenType) -> Iterable[Iterable[ExtraColumn] | None]:
        """Provide extra columns for the print view"""

    @hookspec
    def get_extra_tournament_exporters(self) -> Iterable[Iterable[AbstractTournamentExporter]]:
        """Provide extra exporting formats for tournaments"""
