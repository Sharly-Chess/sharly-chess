from typing import Iterable, Any, TYPE_CHECKING

from packaging.version import Version

from common.i18n import _
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent, StoredTournament
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_controller import (
    CustomUploadAdminEventController,
)
from plugins.custom_upload.utils import (
    CustomUploadTournamentPluginData,
    CustomUploadUtils,
    CustomUploadEventPluginData,
)
from plugins.hookspec import hookimpl
from plugins.utils import (
    Plugin,
    NavDataTransferItem,
    PluginData,
    TournamentConnectionField,
)
from web.controllers.base_controller import BaseController

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament


class CustomUploadPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Custom upload')

    @property
    def description(self) -> str:
        return _('Upload tournament documents to custom location')

    @property
    def version(self) -> Version:
        return Version('0.1.0')

    def used_by_stored_tournament(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ) -> bool:
        return False

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [
            CustomUploadAdminEventController,
        ]

    @hookimpl
    def get_base_admin_template_context(self) -> dict[str, Any]:
        return {
            'custom_upload_utils': CustomUploadUtils,
        }

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_event_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, CustomUploadEventPluginData

    @hookimpl
    def on_event_duplicated(self, event_database: 'EventDatabase'):
        stored_event = event_database.load_stored_event()
        event_plugin_data = CustomUploadEventPluginData.from_stored_value(
            stored_event.plugin_data.get(PLUGIN_NAME, {})
        )
        event_plugin_data.ftp_password = None
        stored_event.plugin_data[PLUGIN_NAME] = event_plugin_data.to_stored_value()
        event_database.update_stored_event(stored_event)

        for stored_tournament in event_database.load_stored_tournaments():
            old_plugin_data = CustomUploadTournamentPluginData.from_stored_value(
                stored_tournament.plugin_data.get(PLUGIN_NAME, {})
            )
            new_plugin_data = CustomUploadTournamentPluginData(
                server_path=old_plugin_data.server_path,
                documents=old_plugin_data.documents,
            )
            stored_tournament.plugin_data[PLUGIN_NAME] = (
                new_plugin_data.to_stored_value()
            )
            event_database.update_stored_tournament(stored_tournament)

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, CustomUploadTournamentPluginData

    @hookimpl
    def get_tournament_connection_field(
        self, tournament: 'Tournament'
    ) -> TournamentConnectionField | None:
        if not CustomUploadUtils.get_tournament_plugin_data(tournament).documents:
            return None
        return TournamentConnectionField(
            label=_('Custom location'),
            template='/custom_upload_tournament_connection_value.html',
        )

    # ---------------------------------------------------------------------------------
    # Upload
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_nav_data_transfer_items(
        self, event: 'Event'
    ) -> Iterable[NavDataTransferItem]:
        has_upload_error = False

        return [
            NavDataTransferItem(
                key='custom_upload',
                title=_('Custom location'),
                icon_path='/images/server.svg',
                modal_route_name='custom-upload-modal',
                has_upload_error=has_upload_error,
            )
        ]
