from types import ModuleType
from typing import Any, TYPE_CHECKING, override, Optional, Iterable

from packaging.version import Version

from common.i18n import _
from data.input_output import TournamentImporter
from database.sqlite.event.event_database import EventDatabase
from plugins.chessevent import migrations, PLUGIN_NAME
from plugins.chessevent.chessevent_controller import ChessEventController
from plugins.chessevent.tournament_importer.importer import ChessEventTournamentImporter
from plugins.chessevent.utils import ChessEventUtils
from plugins.hookspec import hookimpl
from plugins.migration import PluginMigrationManager
from plugins.utils import Plugin

from web.controllers.base_controller import WebContext, BaseController

if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import BaseStoredEvent, StoredEvent
    from database.sqlite.event.event_store import StoredTournament


class ChessEventPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('ChessEvent')

    @property
    def description(self) -> str:
        return _(
            'Support for the ChessEvent platform used '
            'for organising tournaments in France.'
        )

    @property
    def version(self) -> Version:
        return Version('0.1.0')

    @override
    @property
    def default_is_enabled(self) -> bool:
        return False

    @override
    @property
    def base_migration_module(self) -> ModuleType:
        return migrations

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_event_migration_manager(
        self, event_database: EventDatabase
    ) -> PluginMigrationManager:
        return self.get_migration_manager(event_database)

    @hookimpl
    def get_controllers(self) -> Iterable[type[BaseController]]:
        return [ChessEventController]

    # ---------------------------------------------------------------------------------
    # Input-Output
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_tournament_importers(self, importers: list[type[TournamentImporter]]):
        importers.append(ChessEventTournamentImporter)

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def augment_event_after_db_fetch(
        self, stored_event: 'BaseStoredEvent', row: dict[str, Any]
    ):
        stored_event.plugin_data[self.id] = {
            'chessevent_user_id': row.get('chessevent_user_id', None),
            'chessevent_password': row.get('chessevent_password', None),
            'chessevent_event_id': row.get('chessevent_event_id', None),
        }

    @hookimpl
    def event_data_for_db_write(self, stored_event: 'StoredEvent') -> dict[str, Any]:
        td = stored_event.plugin_data
        return {
            'chessevent_user_id': self.get_data(td, 'chessevent_user_id'),
            'chessevent_password': self.get_data(td, 'chessevent_password'),
            'chessevent_event_id': self.get_data(td, 'chessevent_event_id'),
        }

    @hookimpl
    def get_event_card_block_template(self) -> str:
        return '/chessevent_event_card_block.html'

    @hookimpl
    def get_event_form_fields_template(self) -> str:
        return '/chessevent_event_form_fields.html'

    @hookimpl
    def get_event_form_data(self, event: Optional['Event']) -> dict[str, Any]:
        if not event:
            return {
                'chessevent_user': '',
                'chessevent_password': '',
                'chessevent_event_id': '',
            }

        return {
            'chessevent_user': WebContext.value_to_form_data(
                self.get_data(event.plugin_data, 'chessevent_user_id', '')
            ),
            'chessevent_password': WebContext.value_to_form_data(
                self.get_data(event.plugin_data, 'chessevent_password', '')
            ),
            'chessevent_event_id': WebContext.value_to_form_data(
                self.get_data(event.plugin_data, 'chessevent_event_id', '')
            ),
        }

    @hookimpl
    def get_validated_event_form_fields(
        self,
        action: str,
        event: 'Event | None',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        chessevent_user_id = WebContext.form_data_to_str(data, 'chessevent_user')
        chessevent_password = WebContext.form_data_to_str(
            data, field := 'chessevent_password'
        )
        if chessevent_user_id and not chessevent_password:
            errors[field] = _('Please enter a password for the ChessEvent connection.')
        chessevent_event_id = WebContext.form_data_to_str(data, 'chessevent_event_id')

        # Keep data other than these two fields (such as file upload times)
        previous_data = event.plugin_data.get(self.id, {}) if event else {}

        return {
            self.id: previous_data
            | {
                'chessevent_user_id': chessevent_user_id,
                'chessevent_password': chessevent_password,
                'chessevent_event_id': chessevent_event_id,
            }
        }

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def augment_tournament_after_db_fetch(
        self, stored_tournament: 'StoredTournament', row: dict[str, Any]
    ):
        stored_tournament.plugin_data[self.id] = {
            'chessevent_user_id': row['chessevent_user_id'],
            'chessevent_password': row['chessevent_password'],
            'chessevent_event_id': row['chessevent_event_id'],
            'chessevent_tournament_name': row['chessevent_tournament_name'],
            'chessevent_last_sync': row['chessevent_last_sync'],
            'chessevent_status': row['chessevent_status'],
        }

    @hookimpl
    def tournament_data_for_db_write(
        self, stored_tournament: 'StoredTournament'
    ) -> dict[str, Any]:
        td = stored_tournament.plugin_data or {}
        if PLUGIN_NAME not in td:
            return {}
        return {
            'chessevent_user_id': self.get_data(td, 'chessevent_user_id', None),
            'chessevent_password': self.get_data(td, 'chessevent_password', None),
            'chessevent_event_id': self.get_data(td, 'chessevent_event_id', None),
            'chessevent_tournament_name': self.get_data(
                td, 'chessevent_tournament_name', ''
            ),
            'chessevent_last_sync': self.get_data(td, 'chessevent_last_sync', None),
            'chessevent_status': self.get_data(td, 'chessevent_status', None),
        }

    @hookimpl
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        return (
            '/chessevent_tournament_card_block.html',
            {'chessevent_utils': ChessEventUtils},
        )

    @hookimpl
    def get_tournament_tab_action_menu_items_template(self) -> str:
        return '/chessevent_tournament_tab_action_menu_items.html'
