from pathlib import Path
from data.player import Player
import pluggy  # type: ignore
from typing import NamedTuple, Any
from collections.abc import Iterable, Callable

from common import APP_NAME
from data.util import PrintDocument
from web.controllers.index_controller import BaseController

hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)

class ExtraColumn(NamedTuple):
    insertion_index: int
    title: str
    classes: str
    value: Callable[
        [Any], str
    ]

class AppHookSpecs:
    """Holds all hookspecs for this application"""

    @hookspec
    def get_controllers(self) -> Iterable[Iterable[BaseController] | None]:
        """Provide controllers for the application"""
        
    @hookspec
    def get_templates_path(self) -> Iterable[Iterable[Path] | None]:
        """Provide base path to any provided templates"""
        
    @hookspec
    def get_player_search_template(self) -> Iterable[str]:
        """Provide a path to the player search template"""

    @hookspec
    def augment_player(self, player: Player):
        """Add plugin specific data to a player"""
        
    @hookspec
    def get_extra_print_view_columns(self, document: PrintDocument) -> Iterable[Iterable[ExtraColumn] | None]:
        """Provide extra columns for the print view"""
