from typing import TYPE_CHECKING, Iterable

from packaging.version import Version

from data.event import Event
from plugins.hookspec import hookimpl, hookspec
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_admin_controller import SCEAdminController
from plugins.sce.utils import (
    SCETournamentPluginData,
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCEUtils,
    SCEPlayerSyncData,
)
from plugins.utils import (
    PluginData,
    HiddenPlugin,
    NavDataTransferItem,
)
from web.controllers.base_controller import BaseController

if TYPE_CHECKING:
    from data.player import TournamentPlayer, Player
    from database.sqlite.event.event_store import (
        StoredEvent,
        StoredTournament,
        StoredPlayer,
    )


class SCEPluginHooks:
    @hookspec
    def augment_sce_player_sync_data_from_player(
        self,
        player: 'TournamentPlayer',
        sync_data: SCEPlayerSyncData,
    ):
        """Augment SCE player shared data from a player."""

    @hookspec
    def augment_stored_player_from_player_sync_data(
        self,
        stored_player: 'StoredPlayer',
        sync_data: SCEPlayerSyncData,
    ):
        """Augment a stored player from SCE player shared data."""

    @hookspec(firstresult=True)
    def get_sce_national_id_player_field_label(self) -> str | None:
        """Label used for the 'national_id' player field in the conflict modal."""


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
    def hookspecs(self) -> type | None:
        return SCEPluginHooks

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

    @hookimpl
    def on_player_deleted(self, player: 'Player'):
        sce_player_id = SCEUtils.get_player_plugin_data(player).id
        if not sce_player_id:
            return
        event = player.event
        plugin_data = SCEUtils.get_event_plugin_data(event)
        plugin_data.deleted_player_ids.append(sce_player_id)
        SCEUtils.update_event_plugin_data(event, plugin_data)

    @hookimpl(tryfirst=True)
    def get_nav_data_transfer_items(
        self, event: 'Event'
    ) -> Iterable[NavDataTransferItem]:
        status = SCEUtils.resolve_event_status(event)
        has_error = False
        if status.alert_message:
            has_error = True
        else:
            for tournament in event.tournaments:
                plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
                if not plugin_data.id:
                    continue
                if plugin_data.conflict_sync_data or any(
                    status.notify_error_status
                    for status in SCEUtils.resolve_tournament_upload_statuses(
                        tournament
                    )
                ):
                    has_error = True
                    break
                for player in tournament.tournament_players:
                    player_plugin_data = SCEUtils.get_player_plugin_data(player)
                    if player_plugin_data.id and player_plugin_data.conflict_sync_data:
                        has_error = True
                        break
        return [
            NavDataTransferItem(
                key='sce_data_transfer',
                title='Sharly-Chess.com',
                icon_path='/images/sharly-chess-events.ico',
                modal_route_name='sce-sync-modal',
                has_upload_error=has_error,
            )
        ]
