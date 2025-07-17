from types import ModuleType
from typing import Any, TYPE_CHECKING, override, Optional

from packaging.version import Version

from common.i18n import _
from database.sqlite.event.event_database import EventDatabase
from plugins.chessevent import migrations, PLUGIN_NAME
from plugins.chessevent.engine.chessevent_engine import ChessEventEngine
from plugins.chessevent.utils import ChessEventUtils
from plugins.hookspec import hookimpl
from plugins.migration import PluginMigrationManager
from plugins.utils import PluginEngineArgument, Plugin

from web.controllers.base_controller import WebContext

if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import BaseStoredEvent, StoredEvent
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


class ChessEventPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return 'ChessEvent'

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

    # TODO remove this hook after having integrated ChessEvent into the web UI
    @hookimpl
    def get_engine_argument(self) -> PluginEngineArgument:
        return PluginEngineArgument(
            'c',
            'chessevent',
            'download Papi files from Chess Event',
            ChessEventEngine,
        )

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def augment_event_after_db_fetch(
        self, stored_event: 'BaseStoredEvent', row: dict[str, Any]
    ):
        if not stored_event.plugin_data:
            stored_event.plugin_data = {}
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
    def get_event_info_rows_template(self) -> str:
        return '/chessevent_event_info_rows.html'

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
                'chessevent_user_id': '',
                'chessevent_password': '',
                'chessevent_event_id': '',
            }

        return {
            'chessevent_user_id': WebContext.value_to_form_data(
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
        chessevent_user_id = WebContext.form_data_to_str(data, 'chessevent_user_id')
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
        if not stored_tournament.plugin_data:
            stored_tournament.plugin_data = {}
        stored_tournament.plugin_data[self.id] = {
            'chessevent_user_id': row.get('chessevent_user_id', ''),
            'chessevent_password': row.get('chessevent_password'),
            'chessevent_event_id': row.get('chessevent_event_id'),
            'chessevent_tournament_name': row['chessevent_tournament_name'],
            'chessevent_last_download_md5': row['chessevent_last_download_md5'],
        }

    @hookimpl
    def tournament_data_for_db_write(
        self, stored_tournament: 'StoredTournament'
    ) -> dict[str, Any]:
        td = stored_tournament.plugin_data
        return {
            'chessevent_user_id': self.get_data(td, 'chessevent_user_id', None),
            'chessevent_password': self.get_data(td, 'chessevent_password', None),
            'chessevent_event_id': self.get_data(td, 'chessevent_event_id', None),
            'chessevent_tournament_name': self.get_data(
                td, 'chessevent_tournament_name', ''
            ),
        }

    @hookimpl
    def on_tournament_init(self, tournament: 'Tournament'):
        pd = tournament.stored_tournament.plugin_data
        if not self.get_data(pd, 'chessevent_user_id') or not self.get_data(
            pd, 'chessevent_password'
        ):
            tournament.event.add_debug(
                _('ChessEvent connection not defined.'), tournament=tournament
            )
        elif not self.get_data(pd, 'chessevent_event_id'):
            tournament.event.add_debug(
                _('ChessEvent event not set.'), tournament=tournament
            )
        elif not self.get_data(pd, 'chessevent_tournament_name'):
            tournament.event.add_warning(
                _('ChessEvent tournament name not set.'), tournament=tournament
            )

    @hookimpl
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        return (
            '/chessevent_tournament_form_fields.html',
            {},
        )

    @hookimpl
    def get_tournament_form_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> dict[str, Any]:
        if not tournament:
            return {
                'chessevent_user_id': '',
                'chessevent_password': '',
                'chessevent_event_id': '',
                'chessevent_tournament_name': '',
            }

        return {
            'chessevent_user_id': self.get_data(
                tournament.plugin_data,
                'chessevent_user_id',
                '',
            ),
            'chessevent_password': self.get_data(
                tournament.plugin_data, 'chessevent_password', ''
            ),
            'chessevent_event_id': self.get_data(
                tournament.plugin_data, 'chessevent_event_id', ''
            ),
            'chessevent_tournament_name': self.get_data(
                tournament.plugin_data, 'chessevent_tournament_name', ''
            ),
        }

    @hookimpl
    def get_validated_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament | None',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        chessevent_user_id = WebContext.form_data_to_str(data, 'chessevent_user_id')
        chessevent_password = WebContext.form_data_to_str(data, 'chessevent_password')
        chessevent_event_id = WebContext.form_data_to_str(data, 'chessevent_event_id')
        chessevent_tournament_name = WebContext.form_data_to_str(
            data, 'chessevent_tournament_name'
        )

        # Keep data other than these two fields (such as file upload times)
        previous_data = tournament.plugin_data.get(self.id, {}) if tournament else {}

        return {
            self.id: previous_data
            | {
                'chessevent_user_id': chessevent_user_id,
                'chessevent_password': chessevent_password,
                'chessevent_event_id': chessevent_event_id,
                'chessevent_tournament_name': chessevent_tournament_name,
            }
        }

    @hookimpl
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        return (
            '/chessevent_tournament_card_block.html',
            {'chessevent_utils': ChessEventUtils},
        )
