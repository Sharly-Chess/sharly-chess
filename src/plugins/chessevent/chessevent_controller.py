from typing import Any

from litestar import get, patch
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common import format_timestamp_date_time, SharlyChessException
from common.exception import ImporterError
from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from plugins.chessevent.tournament_importer.importer import (
    ChessEventTournamentImporter,
    ChessEventSyncTournamentImporter,
)
from plugins.chessevent.tournament_importer.options import (
    ChessEventEventOption,
    ChessEventUserOption,
    ChessEventPasswordOption,
    ChessEventTournamentOption,
)
from plugins.chessevent.utils import ChessEventUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import EventGuard, ActionGuard


logger = get_logger()


class ChessEventController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.UPDATE_PLAYERS),
    ]

    @staticmethod
    def _chessevent_sync_modal_context(
        tournament: Tournament | None = None,
    ) -> dict[str, Any]:
        return {
            'chessevent_utils': ChessEventUtils,
            'format_timestamp_date_time': format_timestamp_date_time,
            'chessevent_importer': ChessEventTournamentImporter(),
            'tournament': tournament,
        }

    @classmethod
    def _render_sync_modal(cls, web_context: BaseEventAdminWebContext):
        return HTMXTemplate(
            template_name='/chessevent_sync_modal.html',
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
            context=(
                web_context.template_context | cls._chessevent_sync_modal_context()
            ),
        )

    @get(
        path='/chessevent/sync-modal/{event_uniq_id:str}',
        name='chessevent-sync-modal',
    )
    async def chessevent_sync_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_sync_modal(web_context)

    @staticmethod
    def _sync_tournament_with_chessevent(tournament: Tournament):
        status = ChessEventUtils.resolve_tournament_status(tournament)
        if status.sync_disabled_message:
            return
        importer = ChessEventSyncTournamentImporter(
            [
                ChessEventEventOption(ChessEventUtils.resolve_event_id(tournament)),
                ChessEventUserOption(ChessEventUtils.resolve_user_id(tournament)),
                ChessEventPasswordOption(ChessEventUtils.resolve_password(tournament)),
                ChessEventTournamentOption(
                    ChessEventUtils.resolve_tournament_name(tournament)
                ),
            ]
        )
        try:
            importer.load_tournament(tournament.event, tournament)
        except ImporterError:
            """Already repercuted in the status."""
        except SharlyChessException as error:
            logger.error(
                'An error occurred while synchronizing '
                'the tournament [%s] with ChessEvent:\n%s',
                tournament.name,
                error,
            )

    @patch(
        path='/chessevent/sync-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='chessevent-sync-tournament',
    )
    async def chessevent_sync_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        self._sync_tournament_with_chessevent(web_context.get_admin_tournament())
        web_context = TournamentAdminWebContext(
            request, tournament_id, reload_event=True
        )
        return HTMXTemplate(
            template_name='/chessevent_sync_modal_row.html',
            context=(
                web_context.template_context
                | self._chessevent_sync_modal_context(
                    web_context.get_admin_tournament()
                )
            ),
        )

    @patch(
        path='/chessevent/sync-all-tournaments/{event_uniq_id:str}',
        name='chessevent-sync-all-tournaments',
    )
    async def chessevent_sync_all_tournaments(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        for tournament in event.tournaments:
            self._sync_tournament_with_chessevent(tournament)
        web_context = BaseEventAdminWebContext(request, reload_event=True)
        return self._render_sync_modal(web_context)
