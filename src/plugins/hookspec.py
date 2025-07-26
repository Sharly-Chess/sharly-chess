from collections.abc import Callable
from decimal import Decimal
from collections.abc import Iterable
from typing import Any, TYPE_CHECKING, Optional

from litestar.plugins.htmx import HTMXRequest
import apluggy as pluggy  # type: ignore

from common import APP_NAME

from utils.enum import ScreenType
from plugins.utils import (
    ExtraAdminColumn,
    ExtraColumn,
    PluginEngineArgument,
    PluginNavBarItem,
)

if TYPE_CHECKING:
    from data.input_output import DataSource
    from data.pairings.variations import SwissVariation
    from data.player import Player
    from data.print_documents import PrintDocument, PlayerSplitter
    from data.prize.player_filter_options import PlayerFilterOption
    from data.prize.player_filters import PlayerFilter
    from data.tie_breaks import TieBreak
    from data.tournament import Tournament
    from data.event import Event
    from database.access.papi.papi_store import StoredPlayer
    from database.sqlite.event.event_database import EventDatabase
    from database.sqlite.event.event_store import (
        BaseStoredEvent,
        StoredEvent,
        StoredTournament,
    )
    from database.sqlite.local_source_database.databases import LocalSourceDatabase
    from plugins.migration import PluginMigrationManager
    from web.controllers.base_controller import BaseController
    from web.controllers.admin.player_admin_controller import PlayerAdminWebContext

hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)

# pylint: disable=empty-body
# mypy: disable-error-code=empty-body


class AppHookSpecs:
    """Holds all hookspecs for this application"""

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_event_migration_manager(
        self, event_database: 'EventDatabase'
    ) -> 'PluginMigrationManager':
        """Provide a migration manager for event databases"""

    @hookspec
    def get_controllers(self) -> Iterable[type['BaseController']]:
        """Provide controllers for the application"""

    @hookspec
    def get_base_admin_template_context(self) -> dict[str, Any]:
        """Provide additional template context for AdminWebContext"""

    # TODO remove this hook after having integrated ChessEvent into the web UI
    @hookspec
    def get_engine_argument(self) -> PluginEngineArgument:
        """Provide an engine argument"""

    # ---------------------------------------------------------------------------------
    # Data sources
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_data_sources(self, data_sources: list[type['DataSource']]):
        """Provide extra data sources."""

    @hookspec
    def insert_local_source_databases(
        self, databases: list[type['LocalSourceDatabase']]
    ):
        """Provide extra local source databases."""

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_db_player_fields(self) -> list[str]:
        """Provide addition column field names to read from the database"""

    @hookspec
    def augment_player_after_db_fetch(
        self, stored_player: 'StoredPlayer', row: dict[str, Any]
    ) -> list[str]:
        """Add plugin specific data to a player after they are fetched from the database"""

    @hookspec
    def player_data_for_db_write(self, player: 'Player') -> dict[str, Any]:
        """Provide addition column data for players when writing to the database"""

    @hookspec
    def get_player_admin_template_context(
        self, web_context: 'PlayerAdminWebContext'
    ) -> dict[str, Any]:
        """Provide additional template context for rendering in PlayerAdminController"""

    @hookspec
    def get_player_form_fields_template(self) -> str:
        """Provide a path to a template containing additional player form fields"""

    @hookspec
    def get_player_form_data(
        self, plugin_data: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Provide form data for the additional player form fields"""

    @hookspec
    def validate_player_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        """Validate the additional player form fields. Add the errors to the *errors* dict."""

    @hookspec
    def get_player_form_fields(self, data: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Get the fields from the player form data."""

    @hookspec
    async def augment_player_after_search(
        self, stored_player: 'StoredPlayer', data_source: 'DataSource'
    ):
        """Add plugin specific data to a player after a successful player search"""

    @hookspec
    def set_player_default_ratings(self, federation: str, player: 'Player'):
        """Set default ratings for an unrated player when they are added to an event"""

    @hookspec(firstresult=True)
    def is_tournament_participation_possible(
        self, tournament: 'Tournament', player: 'Player'
    ) -> str | None:
        """Test if a player can participate in a tournament"""

    @hookspec
    def get_extra_player_columns(self) -> Iterable[ExtraAdminColumn]:
        """Provide additional columns for the player table view"""

    @hookspec
    def player_filters(
        self,
        web_context: 'PlayerAdminWebContext',
        template_context: dict[str, Any],
    ) -> list[Callable[['Player'], bool]]:
        """List of condition to filter players based on plugin values."""

    @hookspec
    def clear_player_filters(self, request: HTMXRequest):
        """Clear any filters set on the admin players tab"""

    @hookspec(firstresult=True)
    def player_club_sort_key(self, player: 'Player') -> tuple:
        """Returns a sort key for sorting the admin player list by club"""

    @hookspec
    def get_extra_players_datasheet_columns(self) -> Iterable[ExtraColumn]:
        """Provide extra columns for the player download datasheets"""

    @hookspec
    def get_extra_players_update_columns(self) -> Iterable[ExtraAdminColumn]:
        """Provide additional columns for the players update view"""

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookspec
    def augment_event_after_db_fetch(
        self, stored_event: 'BaseStoredEvent', row: dict[str, Any]
    ):
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

    @hookspec
    def get_event_form_data(self, event: Optional['Event']) -> dict[str, Any]:
        """Provide form data for the additional event form fields"""

    @hookspec
    def get_validated_event_form_fields(
        self,
        action: str,
        event: Optional['Event'],
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        """Validate the additional event form fields and return as plugin data"""

    @hookspec(firstresult=True)
    def get_default_prize_currency(self) -> str:
        """Define the prize currency used as default for events
        organized by federations with unknown currencies."""

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookspec
    def on_tournament_data_updated(self, tournament: 'Tournament'):
        """Called when the (publishable) data of a tournament is updated"""

    @hookspec
    def augment_tournament_after_db_fetch(
        self, stored_tournament: 'StoredTournament', row: dict[str, Any]
    ):
        """Add plugin specific data to a StoredTournament after all columns are fetched from the database"""

    @hookspec
    def tournament_data_for_db_write(
        self, stored_tournament: 'StoredTournament'
    ) -> dict[str, Any]:
        """Provide addition column data for tournaments when writing to the database"""

    @hookspec
    def on_tournament_init(self, tournament: 'Tournament'):
        """Do any tournament specific initialisation when a Tournament object is initialised"""

    @hookspec
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        """Provide a path to the template containing additional tournament form fields"""

    @hookspec
    def get_tournament_form_data(
        self,
        event: 'Event',
        tournament: 'Tournament | None',
        action: str,
    ) -> dict[str, Any]:
        """Provide form data for the additional tournament form fields"""

    @hookspec
    def get_validated_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        """Validate the additional tournament form fields and return as plugin data"""

    @hookspec
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        """Provide a path to the template to be added to tournament cards"""

    @hookspec
    def get_tournament_card_menu_items_template(self) -> str:
        """Provide a path to the template to be added to the action menu"""

    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_print_player_splitter_types(
        self, player_splitter_types: list[type['PlayerSplitter']]
    ):
        """Provide print player splitting options"""

    @hookspec
    def get_extra_print_view_columns(
        self, document: 'PrintDocument'
    ) -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    @hookspec
    def get_extra_print_view_css(self, document: 'PrintDocument') -> str:
        """Provide extra CSS for the print view"""

    # ---------------------------------------------------------------------------------
    # Nav bar
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_event_nav_bar_items_and_data(
        self, event: 'Event'
    ) -> tuple[Iterable[PluginNavBarItem], dict[str, Any]]:
        """Provide extra nav bar items"""

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
    def get_extra_tie_break_classes(self) -> list[type['TieBreak']]:
        """Provide extra tournament tie breaks"""

    # ---------------------------------------------------------------------------------
    # Pairings
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_swiss_pairing_variation_types(
        self, variation_types: list[type['SwissVariation']]
    ):
        """Provide extra swiss pairing variations."""

    # ---------------------------------------------------------------------------------
    # Shared utils
    # ---------------------------------------------------------------------------------

    @hookspec(firstresult=True)
    def get_performance_bonus_function(self) -> Callable[[float], int | float]:
        """Provide a function to compute the performance bonus"""

    @hookspec(firstresult=True)
    def get_round_ranking_function(self) -> Callable[[float | Decimal], int]:
        """Provide a function to round a ranking to an integer"""

    # ---------------------------------------------------------------------------------
    # Prizes
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_prize_player_filter_types(
        self, player_filter_types: list[type['PlayerFilter']]
    ):
        """Provide extra player filters for prizes."""

    @hookspec
    def insert_prize_player_filter_option_types(
        self, player_filter_option_types: list[type['PlayerFilterOption']]
    ):
        """Provide the options of the added prize player filters."""
