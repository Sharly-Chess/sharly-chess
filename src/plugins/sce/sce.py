from typing import TYPE_CHECKING

from packaging.version import Version

from plugins.hookspec import hookimpl
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_admin_controller import SCEAdminController
from plugins.sce.utils import (
    SCETournamentPluginData,
    SCEEventPluginData,
    SCEPlayerPluginData,
)
from plugins.utils import (
    PluginData,
    HiddenPlugin,
)
from web.controllers.base_controller import BaseController

if TYPE_CHECKING:
    from database.sqlite.event.event_store import StoredEvent, StoredTournament


class SCEPlugin(HiddenPlugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return 'Sharly-Chess.com'

    @property
    def version(self) -> Version:
        return Version('1.0.0')

    @property
    def default_is_enabled(self) -> bool:
        return True

    @property
    def default_event_is_enabled(self) -> bool:
        return False

    @property
    def is_hidden(self) -> bool:
        return True

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [SCEAdminController]

    def used_by_stored_tournament(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ) -> bool:
        return bool(stored_tournament.plugin_data.get(PLUGIN_NAME, {}).get('id'))

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_event_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, SCEEventPluginData

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, SCETournamentPluginData

    # ---------------------------------------------------------------------------------
    # Player
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_player_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, SCEPlayerPluginData
