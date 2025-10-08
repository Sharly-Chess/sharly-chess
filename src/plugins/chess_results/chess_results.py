from types import ModuleType
from typing import Any, TYPE_CHECKING, Optional, override

from packaging.version import Version

from common.i18n import _
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.chess_results.chess_results_background_uploader import (
    EventLoader,
    ChessResultsBackgroundUploader,
)
from plugins.chess_results.utils import (
    CHESS_RESULTS_DEFAULT_UPLOAD_DELAY,
    CHESS_RESULTS_MIN_UPLOAD_DELAY,
    ChessResultsUtils,
)
from database.sqlite.event.event_database import EventDatabase
from plugins.chess_results import PLUGIN_NAME, migrations
from plugins.chess_results.chess_results_event_controller import (
    ChessResultsAdminEventController,
)
from plugins.hookspec import hookimpl
from plugins.migration import PluginMigrationManager
from plugins.utils import (
    Plugin,
)

from web.controllers.base_controller import BaseController, WebContext


if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import StoredEvent
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


class ChessResultsPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('ChessResults')

    @property
    def description(self) -> str:
        return _('Uploading of tournaments to chess-results.com.')

    @property
    def version(self) -> Version:
        return Version('1.0.0')

    @override
    @property
    def default_is_enabled(self) -> bool:
        return False

    @override
    @property
    def is_state_editable(self) -> bool:
        return True

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

    @property
    def controllers(self) -> list[type[BaseController]]:
        return [
            ChessResultsAdminEventController,
        ]

    @hookimpl
    def get_base_admin_template_context(self) -> dict[str, Any]:
        return {
            'CHESS_RESULTS_DEFAULT_UPLOAD_DELAY': CHESS_RESULTS_DEFAULT_UPLOAD_DELAY,
        }

    # ---------------------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------------------

    @hookimpl
    def augment_event_after_db_fetch(
        self, stored_event: 'StoredEvent', row: dict[str, Any]
    ):
        stored_event.plugin_data[self.id] = {
            'auto_upload': row.get('chess_results_auto_upload', False),
            'auto_upload_delay': row.get('chess_results_auto_upload_delay', None),
        }

    @hookimpl
    def event_data_for_db_write(self, stored_event: 'StoredEvent') -> dict[str, Any]:
        td = stored_event.plugin_data
        return {
            'chess_results_auto_upload': int(self.get_data(td, 'auto_upload') or False),
            'chess_results_auto_upload_delay': self.get_data(td, 'auto_upload_delay'),
        }

    @hookimpl
    def get_event_card_block_template(self) -> str:
        return '/chess_results_event_card_block.html'

    @hookimpl
    def get_event_form_fields_template(self) -> str:
        return '/chess_results_event_form_fields.html'

    @hookimpl
    def get_event_form_data(self, event: Optional['Event']) -> dict[str, Any]:
        if not event:
            return {
                'auto_upload': 'off',
                'auto_upload_delay': '',
            }

        return {
            'auto_upload': WebContext.value_to_form_data(
                bool(self.get_data(event.plugin_data, 'auto_upload', False))
            ),
            'auto_upload_delay': WebContext.value_to_form_data(
                self.get_data(event.plugin_data, 'auto_upload_delay', '')
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
        auto_upload = WebContext.form_data_to_bool(data, 'auto_upload')
        auto_upload_delay = WebContext.form_data_to_int(
            data, field := 'auto_upload_delay'
        )
        if auto_upload_delay and auto_upload_delay < CHESS_RESULTS_MIN_UPLOAD_DELAY:
            errors[field] = _(
                'The delay must be at least {min_delay} minutes to avoid overloading the ChessResults server.'
            ).format(min_delay=CHESS_RESULTS_MIN_UPLOAD_DELAY)

        # Keep data other than these two fields
        previous_data = event.plugin_data.get(self.id, {}) if event else {}

        return {
            self.id: previous_data
            | {
                'auto_upload': auto_upload or False,
                'auto_upload_delay': auto_upload_delay,
            }
        }

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def on_tournament_data_updated(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ):
        # This hook being called for most database writes, it needs to be optimized
        if not ChessResultsBackgroundUploader.should_schedule_tournament_upload(
            stored_event, stored_tournament
        ):
            return
        event = EventLoader().load_event(stored_event.uniq_id)
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        tournament = event.tournaments_by_id[tournament_id]
        ChessResultsBackgroundUploader.schedule_upload(tournament)

    @hookimpl
    def augment_tournament_after_db_fetch(
        self, stored_tournament: 'StoredTournament', row: dict[str, Any]
    ):
        stored_tournament.plugin_data[self.id] = {
            'tnr': row.get('chess_results_tnr', ''),
            'creator_id': row.get('chess_results_creator_id', None),
            'auto_upload': SQLiteDatabase.load_bool_or_none_from_database_field(
                row.get('chess_results_auto_upload', None)
            ),
            'last_upload': row.get('chess_results_last_upload', 0.0),
        }

    @hookimpl
    def tournament_data_for_db_write(
        self, stored_tournament: 'StoredTournament'
    ) -> dict[str, Any]:
        data = stored_tournament.plugin_data
        return {
            'chess_results_tnr': self.get_data(data, 'tnr', None),
            'chess_results_creator_id': self.get_data(data, 'creator_id', None),
            'chess_results_auto_upload': self.get_data(data, 'auto_upload', None),
        }

    @hookimpl
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        auto_upload_options: dict[str, str] = {
            '': '',
            WebContext.value_to_form_data(False): _('Disabled'),
        } | {
            WebContext.value_to_form_data(True): _('Enabled'),
        }
        event_auto_upload = bool(self.get_data(event.plugin_data, 'auto_upload', False))
        auto_upload_options[''] = _("Use Event's default - {option}").format(
            option=auto_upload_options[WebContext.value_to_form_data(event_auto_upload)]
        )

        return (
            '/chess_results_tournament_form_fields.html',
            {
                'auto_upload_options': auto_upload_options,
            },
        )

    @hookimpl
    def get_tournament_form_data(
        self,
        event: 'Event',
        tournament: 'Tournament | None',
        action: str,
    ) -> dict[str, Any]:
        if not tournament:
            return {
                'auto_upload': '',
            }

        return {
            'auto_upload': self.get_data(tournament.plugin_data, 'auto_upload', None),
        }

    @hookimpl
    def get_validated_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament | None',
        data: dict[str, str],
        errors: dict[str, str],
    ) -> dict[str, Any]:
        auto_upload = WebContext.form_data_to_bool_or_none(data, 'auto_upload')
        # Keep data other than these two fields (such as file upload times)
        previous_data = tournament.plugin_data.get(self.id, {}) if tournament else {}

        return {
            self.id: previous_data
            | {
                'creator_id': ''
                if action == 'clone'
                else previous_data.get('creator_id', None),
                'auto_upload': auto_upload,
            }
        }

    @hookimpl
    def get_tournament_card_block_template_and_data(self) -> tuple[str, dict[str, Any]]:
        return (
            '/chess_results_tournament_card_block.html',
            {
                'chess_results_utils': ChessResultsUtils,
            },
        )

    @hookimpl
    def get_tournament_tab_action_menu_items_template(self) -> str:
        return '/chess_results_tournament_tab_action_menu_items.html'

    # @hookimpl
    # def signal_tournament_set(
    # self, tournament: 'Tournament', stored_tournament: 'StoredTournament'
    # ) -> str | None:
    # pairing_variation = PairingVariationManager.get_object(
    # stored_tournament.pairing
    # )
    # if blocker := PapiConverter.check_pairing_variation(pairing_variation):
    # return blocker
    # if blocker := PapiConverter.check_rounds(stored_tournament.rounds):
    # return blocker

    # tie_break_type_by_id: dict[str, type[TieBreak]] = TieBreakManager.type_by_id()
    # option_type_by_id: dict[str, type[TieBreakOption]] = (
    # TieBreakOptionManager.type_by_id()
    # )
    # for tie_break_dict in stored_tournament.tie_breaks:
    # assert isinstance(tie_break_dict['type'], str)
    # assert isinstance(tie_break_dict['options'], dict)
    # tie_break_id = tie_break_dict['type']
    # options: list[TieBreakOption] = []
    # for option_id, value in tie_break_dict['options'].items():
    # if option_type := option_type_by_id.get(option_id, None):
    # options.append(option_type(value))
    # if tie_break_type := tie_break_type_by_id.get(tie_break_id, None):
    # tie_break = tie_break_type(options)
    # if blocker := PapiConverter.check_tiebreak(tie_break):
    # return blocker

    # return None
