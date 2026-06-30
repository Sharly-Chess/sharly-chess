from typing import Iterable, Any, TYPE_CHECKING

from packaging.version import Version

from common.i18n import _
from database.sqlite.event.event_store import StoredEvent, StoredTournament
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_controller import (
    CustomUploadAdminEventController,
)
from plugins.custom_upload.utils import (
    CustomUploadTournamentPluginData,
    CustomUploadUtils,
)
from plugins.hookspec import hookimpl
from plugins.utils import Plugin, NavDataTransferItem, PluginData
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
        return _('Custom Upload')

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
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, CustomUploadTournamentPluginData

    @hookimpl
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        return (
            '/custom_upload_tournament_form_fields.html',
            {},
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
