from typing import TYPE_CHECKING

from packaging.version import Version

from common.i18n import _
from plugins.chess960 import PLUGIN_NAME
from plugins.chess960.chess960_controller import (
    Chess960Controller,
    Chess960SvgController,
)
from plugins.chess960.screen_type import Chess960ScreenType
from plugins.chess960.utils import Chess960ScreenPluginData
from plugins.hookspec import hookimpl
from plugins.utils import Plugin, PluginData
from web.controllers.base_controller import BaseController

if TYPE_CHECKING:
    from data.screens.screen_types import ScreenType
    from database.sqlite.event.event_store import StoredEvent, StoredTournament


class Chess960Plugin(Plugin):
    data_class = Chess960ScreenPluginData

    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Chess960')

    @property
    def description(self) -> str:
        return _('Adds a screen showing the Chess960 start position.')

    @property
    def version(self) -> Version:
        return Version('1.0.0')

    @property
    def default_is_enabled(self) -> bool:
        return False

    @property
    def default_event_is_enabled(self) -> bool:
        return False

    def used_by_stored_tournament(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ) -> bool:
        return False

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [
            Chess960Controller,
            Chess960SvgController,
        ]

    @hookimpl
    def get_screen_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, Chess960ScreenPluginData

    @hookimpl
    def insert_screen_types(self, screen_types: list[type['ScreenType']]):
        screen_types.append(Chess960ScreenType)
