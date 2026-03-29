from typing import TYPE_CHECKING, Iterable, Any

from packaging.version import Version

from common.i18n import _
from data.event import Event
from data.loader import EventLoader
from plugins.hookspec import hookimpl, hookspec
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_admin_controller import SCEAdminController
from plugins.sce.sce_background_uploader import (
    should_schedule_auto_upload,
    schedule_upload,
)
from plugins.sce.sce_tournament_results_builder import SCEUploadColumn
from plugins.sce.sce_data import (
    SCETournamentPluginData,
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCEPlayerSyncData,
)
from plugins.sce.utils import SCEUtils
from plugins.utils import (
    PluginData,
    NavDataTransferItem,
    Plugin,
)
from web.controllers.base_controller import BaseController

if TYPE_CHECKING:
    from data.player import TournamentPlayer, Player
    from data.tournament import Tournament
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

    @hookspec
    def add_sce_upload_player_custom_fields(
        self, custom_fields: dict[str, Any], player: 'TournamentPlayer'
    ):
        """Add custom fields to the SCE uploaded players."""

    @hookspec
    def alter_sce_upload_player_columns(self, columns: list[SCEUploadColumn]):
        """Alter the player columns of the SCE results upload."""

    @hookspec
    def alter_sce_upload_ranking_columns(self, columns: list[SCEUploadColumn]):
        """Alter the ranking columns of the SCE results upload."""


class SCEPlugin(Plugin):
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
    def description(self) -> str:
        return _(
            'Integration with the Sharly-Chess.com platform '
            '(online check-in, results upload, etc.).'
        )

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
    def event_form_script_file(self) -> str:
        return '/sce_event_form_script.js'

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

    @hookimpl
    def create_event_button_template(self) -> str:
        return '/sce_event_create_button.html'

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, SCETournamentPluginData

    @hookimpl
    def get_tournament_page_template_context(self) -> dict[str, Any]:
        return {'sce_utils': SCEUtils}

    @hookimpl
    def get_tournament_card_connexion_template(
        self, tournament: 'Tournament'
    ) -> str | None:
        if not SCEUtils.get_tournament_plugin_data(tournament).id:
            return None
        return '/sce_tournament_card_connexion.html'

    @hookimpl
    def on_tournament_data_updated(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ):
        # This hook being called for most database writes, it needs to be optimized
        if not should_schedule_auto_upload(stored_event, stored_tournament):
            return
        event = EventLoader().load_event(stored_event.uniq_id)
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        tournament = event.tournaments_by_id[tournament_id]
        schedule_upload(tournament)

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

    # ---------------------------------------------------------------------------------
    # Nav
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _event_has_sce_error_badge(event: Event) -> bool:
        if SCEUtils.resolve_event_status(event).notify_error_status:
            return True
        if SCEUtils.resolve_last_sync_status(event).notify_error_status:
            return True
        for tournament in event.tournaments:
            if SCEUtils.get_tournament_plugin_data(tournament).upload_failure_id:
                return True
        return False

    @hookimpl(tryfirst=True)
    def get_nav_data_transfer_items(
        self, event: 'Event'
    ) -> Iterable[NavDataTransferItem]:
        return [
            NavDataTransferItem(
                key='sce_data_transfer',
                title='Sharly-Chess.com',
                icon_path='/images/sharly-chess-events.ico',
                modal_route_name='sce-sync-modal',
                has_upload_error=self._event_has_sce_error_badge(event),
            )
        ]
