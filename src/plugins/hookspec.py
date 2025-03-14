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
    from web.controllers.admin.base_event_admin_controller import BaseEventAdminWebContext

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

    @hookspec
    def on_init(self):
        """Provide any initialisation"""

    @hookspec
    def get_controllers(self) -> Iterable[type['BaseController']]:
        """Provide controllers for the application"""

    @hookspec
    def get_templates_path(self) -> Path:
        """Provide base path to any provided templates"""

    @hookspec
    def get_base_admin_context(self) -> dict[str, Any]:
        """Provide plugin context for the AdminWebContext"""

    @hookspec
    def get_player_admin_context(self, web_context: 'BaseEventAdminWebContext') -> dict[str, Any]:
        """Provide plugin context for the BaseEventAdminWebContext"""

    @hookspec
    def get_player_search_template(self) -> str:
        """Provide a path to the player search template"""

    @hookspec
    def get_player_form_fields_template(self) -> str:
        """Provide a path to the template containing player form fields"""

    @hookspec
    def get_player_form_data(
        self, plugin_data: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Provide form data for the player form fields"""

    @hookspec
    def get_validated_player_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str]
    ) -> dict[str, Any]:
        """Validate player form fields"""

    @hookspec
    def get_event_info_rows_template(self) -> str:
        """Provide a path to the template containing event info rows form fields"""

    @hookspec
    def get_event_card_block_template(self) -> str:
        """Provide a path to the template to be added to event cards"""

    @hookspec
    def get_tournament_form_fields_template(self) -> str:
        """Provide a path to the template containing tournament form fields"""

    @hookspec
    def augment_event_after_db_fetch(self, stored_event: 'StoredEvent', row: dict[str, Any]):
        """Add plugin specific data to a stored event after they are fetched from the database"""

    @hookspec
    def event_data_for_db_write(self, stored_event: 'StoredEvent') -> dict[str, Any]:
        """Provide data for event fields to write to the database"""

    @hookspec
    def augment_tournament_after_db_fetch(self, stored_tournament: 'StoredTournament', row: dict[str, Any]):
        """Add plugin specific data to a stored tournaments after they are fetched from the database"""

    @hookspec
    def tournament_data_for_db_write(self, stored_tournament: 'StoredTournament') -> dict[str, Any]:
        """Provide data for tournament fields to write to the database"""

    @hookspec
    def on_tournament_init(self, tournament: 'Tournament'):
        """Do any tournament specific initialisation """
    @hookspec
    def get_tournament_form_data(
        self, tournament: 'Tournament | None',
    ) -> dict[str, Any]:
        """Provide form data for the tournament form fields"""

    @hookspec
    def get_validated_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str]
    ) -> dict[str, Any]:
        """Validate tournament form fields"""

    @hookspec
    def get_db_player_fields(self) -> list[str]:
        """Provide extra fields to read or write to the player database"""

    @hookspec
    def augment_player_after_db_fetch(
        self, player: Player, row: dict[str, Any]
    ) -> list[str]:
        """Add plugin specific data to a player after they are fetched from the database"""

    @hookspec
    def player_data_for_db_write(self, player: Player) -> dict[str, Any]:
        """Provide data for player fields to write to the database"""

    @hookspec
    def augment_player_after_search(self, player: Player):
        """Add plugin specific data to a player"""

    @hookspec
    def set_player_default_ratings(self, federation: str, player: 'Player'):
        """Set default ratings for an unrated player"""

    @hookspec(firstresult=True)
    def is_tournament_participation_possible(
        self, tournament: 'Tournament', player: Player
    ) -> str | None:
        """Test if a player can participate in a tournament"""

    @hookspec
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        """Provide a path to the template to be added to tournament cards"""

    @hookspec
    def get_print_split_options(self) -> Iterable[PrintSplitOption]:
        """Provide print splitting options"""

    @hookspec
    def get_extra_player_columns(self) -> Iterable[ExtraAdminColumn]:
        """Provide extra columns for the print view"""

    @hookspec
    def clear_player_filters(self, request: HTMXRequest):
        """Clear any filters set on the admin players tab"""

    @hookspec
    def filter_player(self, web_context: 'BaseEventAdminWebContext', template_context: dict[str, Any], player: Player) -> bool:
        """Returns True if the player should be in the admin player list, False otherwise """

    @hookspec(firstresult=True)
    def player_club_sort_key(self, player: Player) -> tuple:
        """Returns a sort key for sorting the admin player list by club """

    @hookspec
    def get_extra_print_view_columns(self, document: PrintDocument) -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    @hookspec
    def get_extra_screen_columns(self, screen: ScreenType) -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    @hookspec
    def get_extra_players_datasheet_columns(self) -> Iterable[ExtraColumn]:
        """Provide extra columns for the player download datasheets """

    @hookspec
    def get_extra_tournament_exporters(self) -> list[AbstractTournamentExporter]:
        """Provide extra exporting formats for tournaments"""

    @hookspec
    def get_event_migration_manager(self) -> AbstractPluginMigrationManager:
        """Provide a migration manager for event databases"""

    @hookspec
    def get_engine_argument(self) -> PluginEngineArgument:
        """Provide an engine argument"""

    @hookspec
    def get_extra_tie_break_classes(self) -> list[type['AbstractTieBreak']]:
        """Provide extra tournament tie breaks"""
