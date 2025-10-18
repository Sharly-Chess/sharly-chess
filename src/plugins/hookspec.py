from collections.abc import Callable
from datetime import date
from decimal import Decimal
from collections.abc import Iterable
from typing import Any, TYPE_CHECKING, Optional

from litestar.plugins.htmx import HTMXRequest
import apluggy as pluggy  # type: ignore

from common import APP_NAME

from plugins.utils import (
    ExtraAdminColumn,
    ExtraColumn,
    ExtraStatisticsSection,
    NavUploadItem,
    PluginData,
)
from utils.enum import Result, ScreenType, TournamentRating

if TYPE_CHECKING:
    from data.input_output import DataSource, TournamentExporter, TournamentImporter
    from data.pairings.variations import SwissVariation
    from data.player import Player, PlayerRatingAndType, PlayerRatingType
    from data.print_documents import PrintDocument, PlayerSplitter, QRCodeType
    from data.criteria.player_filter_options import PlayerFilterOption
    from data.criteria.player_filters import PlayerFilter
    from data.tie_breaks import TieBreak
    from data.tournament import Tournament
    from data.event import Event
    from database.sqlite.event.event_store import StoredPlayer
    from database.sqlite.event.event_database import EventDatabase
    from database.sqlite.event.event_store import (
        StoredEvent,
        StoredTournament,
    )
    from database.sqlite.local_source_database.databases import LocalSourceDatabase
    from plugins.migration import PluginMigrationManager
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
    def get_base_admin_template_context(self) -> dict[str, Any]:
        """Provide additional template context for AdminWebContext"""

    # ---------------------------------------------------------------------------------
    # Input-Output
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_data_sources(self, data_sources: list[type['DataSource']]):
        """Provide extra data sources."""

    @hookspec
    def insert_local_source_databases(
        self, databases: list[type['LocalSourceDatabase']]
    ):
        """Provide extra local source databases."""

    @hookspec
    def insert_tournament_exporters(self, exporters: list[type['TournamentExporter']]):
        """Provide extra tournament export options."""

    @hookspec
    def insert_tournament_importers(self, importers: list[type['TournamentImporter']]):
        """Provide extra tournament import options."""

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_player_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        """Get the data class to use to store plugin player values.
        Also provide the ID of the plugin."""

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

    @hookspec(firstresult=True)
    def get_player_rating(
        self,
        tournament_rating: TournamentRating,
        player_rating_type: 'PlayerRatingType',
        player: 'Player',
    ) -> Optional['PlayerRatingAndType']:
        """Get the estimated rating of a player."""

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

    @hookspec(firstresult=True)
    def adjust_category_reference_year(self, reference_date: date) -> int | None:
        """Adjust the reference date for the category"""

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookspec
    def on_event_duplicated(self, event_database: 'EventDatabase'):
        """Called after an event is duplicated"""

    @hookspec
    def get_event_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        """Get the data class to use to store plugin event values.
        Also provide the ID of the plugin."""

    @hookspec
    def get_event_form_fields_template(self) -> str:
        """Returns the path of the template for additional fields of the event modal"""

    @hookspec
    def get_event_form_data(self, event: Optional['Event']) -> dict[str, Any]:
        """Provide form data for the additional event form fields"""

    @hookspec
    def validate_event_form_fields(
        self,
        action: str,
        event: Optional['Event'],
        data: dict[str, str],
        errors: dict[str, str],
    ):
        """Validate the additional event form fields"""

    @hookspec(firstresult=True)
    def get_default_prize_currency(self) -> str:
        """Define the prize currency used as default for events
        organized by federations with unknown currencies."""

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        """Get the data class to use to store plugin tournament values.
        Also provide the ID of the plugin."""

    @hookspec
    def on_tournament_data_updated(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ):
        """Called when the (publishable) data of a tournament is updated"""

    @hookspec
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        """Provide a path to the template containing additional tournament form fields"""

    @hookspec
    def validate_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        """Validate the additional tournament form fields"""

    @hookspec
    def get_tournament_page_template_context(self) -> dict[str, Any]:
        """Get the context used for the templates provided for the tournament page."""

    @hookspec
    def get_tournament_card_connexion_template(
        self, tournament: 'Tournament'
    ) -> str | None:
        """Add a template path for a connexion to display on the tournament cards.
        These templates are displayed in priority in the card.
        Return None if the connexion is undefined."""

    @hookspec
    def get_tournament_card_fields_template(self) -> str:
        """Provide a path to the template of fields to be added to tournament cards."""

    @hookspec
    def get_tournament_card_action_menu_items_template(self) -> str:
        """Path to the template to be added to the 'Actions' menu of the tournament card"""

    @hookspec
    def get_tournament_tab_action_menu_items_template(self) -> str:
        """Path to the template to be added to the 'Actions' menu of the tournament tab."""

    @hookspec(firstresult=True)
    def get_tournament_tie_break_warning_message(
        self, tournament: 'Tournament', tie_break: 'TieBreak'
    ) -> str | None:
        """Warning message for a tie-break on a tournament."""

    @hookspec
    def signal_tournament_set(
        self, event: 'Event', stored_tournament: 'StoredTournament'
    ) -> str | None:
        """A signal sent when a tournament is updated. Returns a string to be displayed to the user"""

    @hookspec
    def signal_special_result_set(
        self, tournament: 'Tournament | None', result: Result
    ) -> str | None:
        """A signal sent when a special result is set. Returns a string to be displayed to the user"""

    # ---------------------------------------------------------------------------------
    # Upload
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_nav_upload_items(self, event: 'Event') -> Iterable['NavUploadItem']:
        """Provide upload items for the menu"""

    # ---------------------------------------------------------------------------------
    # Printing
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_print_player_splitter_types(
        self, player_splitter_types: list[type['PlayerSplitter']]
    ):
        """Provide print player splitting options"""

    @hookspec
    def insert_print_qrcode_types(self, qrcode_types: list[type['QRCodeType']]):
        """Provide QR Code options"""

    @hookspec
    def get_extra_print_view_columns(
        self, document: 'PrintDocument'
    ) -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    @hookspec
    def get_extra_print_view_css(self, document: 'PrintDocument') -> str:
        """Provide extra CSS for the print view"""

    @hookspec
    def get_extra_statistics_sections(
        self, document: 'PrintDocument', tournaments: list['Tournament']
    ) -> Iterable[ExtraStatisticsSection]:
        """Provide extra sections for the statistics print view"""

    # ---------------------------------------------------------------------------------
    # User screens
    # ---------------------------------------------------------------------------------

    @hookspec
    def get_extra_screen_columns(self, screen: 'ScreenType') -> Iterable[ExtraColumn]:
        """Provide extra columns for the print view"""

    # ---------------------------------------------------------------------------------
    # Tie breaks
    # ---------------------------------------------------------------------------------

    @hookspec
    def insert_tie_break_types(self, tie_break_types: list[type['TieBreak']]):
        """Provide extra tournament tie breaks."""

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
    def insert_player_filter_types(
        self, player_filter_types: list[type['PlayerFilter']]
    ):
        """Provide extra player filters for prizes."""

    @hookspec
    def insert_player_filter_option_types(
        self, player_filter_option_types: list[type['PlayerFilterOption']]
    ):
        """Provide the options of the added prize player filters."""
