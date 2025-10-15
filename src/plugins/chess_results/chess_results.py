from typing import Any, TYPE_CHECKING, Iterable, override

from packaging.version import Version

from common.i18n import _
from database.sqlite.event.event_database import EventDatabase
from plugins.chess_results.chess_results_background_uploader import (
    ChessResultsUploadStatus,
    EventLoader,
    ChessResultsBackgroundUploader,
)
from plugins.chess_results.utils import (
    CHESS_RESULTS_DEFAULT_UPLOAD_DELAY,
    CHESS_RESULTS_MIN_UPLOAD_DELAY,
    ChessResultsConfigPluginData,
    ChessResultsEventPluginData,
    ChessResultsTournamentPluginData,
    ChessResultsUtils,
)
from plugins.chess_results import PLUGIN_NAME
from plugins.chess_results.chess_results_event_controller import (
    ChessResultsAdminEventController,
)
from plugins.hookspec import hookimpl
from plugins.utils import (
    NavUploadItem,
    Plugin,
    PluginData,
)

from web.controllers.base_controller import BaseController, WebContext


if TYPE_CHECKING:
    from data.event import Event
    from database.sqlite.event.event_store import StoredEvent
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


class ChessResultsPlugin(Plugin[ChessResultsConfigPluginData]):
    data_class = ChessResultsConfigPluginData

    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Chess-Results.com')

    @property
    def description(self) -> str:
        return _('Uploading of tournaments to Chess-Results.com.')

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

    # ---------------------------------------------------------------------------------
    # Initialisation and configuration
    # ---------------------------------------------------------------------------------

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
    def on_event_duplicated(self, event_database: EventDatabase):
        stored_tournaments = event_database.load_stored_tournaments()
        for stored_tournament in stored_tournaments:
            old_plugin_data = ChessResultsTournamentPluginData.from_stored_value(
                stored_tournament.plugin_data.get(PLUGIN_NAME, {})
            )

            # Only retain the remark setting
            # We don't retain the auto_upload setting since that would cause an immediate upload of the tournament since
            # we don't need an other fields to be set in order to do an upload.
            new_plugin_data = ChessResultsTournamentPluginData(
                remark=old_plugin_data.remark,
                remark_default=old_plugin_data.remark_default,
            )
            stored_tournament.plugin_data[PLUGIN_NAME] = (
                new_plugin_data.to_stored_value()
            )
            event_database.update_stored_tournament(stored_tournament)

    @hookimpl
    def get_event_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, ChessResultsEventPluginData

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
    def get_event_form_fields_template(self) -> str:
        return '/chess_results_event_form_fields.html'

    @hookimpl
    def validate_event_form_fields(
        self,
        action: str,
        event: 'Event | None',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        auto_upload_delay = WebContext.form_data_to_int(
            data, field := 'auto_upload_delay'
        )
        if auto_upload_delay and auto_upload_delay < CHESS_RESULTS_MIN_UPLOAD_DELAY:
            errors[field] = _(
                'The delay must be at least {min_delay} minutes to avoid overloading the Chess-Results server.'
            ).format(min_delay=CHESS_RESULTS_MIN_UPLOAD_DELAY)

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, ChessResultsTournamentPluginData

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
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        auto_upload_options: dict[str, str] = {
            '': '',
            WebContext.value_to_form_data(False): _('Disabled'),
        } | {
            WebContext.value_to_form_data(True): _('Enabled'),
        }
        event_auto_upload = ChessResultsUtils.get_event_plugin_data(event).auto_upload
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
    def get_tournament_page_template_context(self) -> dict[str, Any]:
        return {'chess_results_utils': ChessResultsUtils}

    @hookimpl
    def get_tournament_card_connexion_template(
        self, tournament: 'Tournament'
    ) -> str | None:
        if not ChessResultsUtils.get_tournament_plugin_data(tournament).tnr:
            return None
        return '/chess_results_tournament_card_connexion.html'

    # ---------------------------------------------------------------------------------
    # Upload
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_nav_upload_items(self, event: 'Event') -> Iterable[NavUploadItem]:
        has_upload_error = False
        statuses = ChessResultsBackgroundUploader.upload_status_messages
        tournaments = event.tournaments
        for tournament in tournaments:
            result = statuses.get(
                ChessResultsBackgroundUploader.result_id(event.uniq_id, tournament.id),
                None,
            )
            if result and result.status == ChessResultsUploadStatus.ERROR:
                has_upload_error = True
                break

        return [
            NavUploadItem(
                key='chess_results_upload',
                title=_('Chess-Results.com'),
                icon_path='/images/chess-results.png',
                modal_route_name='chess-results-upload-modal',
                has_upload_error=has_upload_error,
            )
        ]
