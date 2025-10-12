from functools import partial
from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common import format_timestamp_date_time
from data.access_levels.actions import AuthAction
from plugins.chess_results import PLUGIN_NAME
from plugins.chess_results.chess_results_background_uploader import (
    ChessResultsBackgroundUploader,
)
from plugins.chess_results.utils import ChessResultsUtils
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessResultsAdminEventController(BaseEventAdminController):
    guards = []

    @get(
        path='/chess-results/chess-results-upload-modal/{event_uniq_id:str}',
        name='chess-results-upload-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_chess_results_upload_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)

        ChessResultsBackgroundUploader.update_eligible_tournaments(
            web_context.get_admin_event()
        )

        return HTMXTemplate(
            template_name='/chess_results_upload_modal.html',
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': ChessResultsBackgroundUploader.result_id,
                'upload_status_messages': ChessResultsBackgroundUploader.upload_status_messages,
                'chess_results_utils': ChessResultsUtils,
            },
        )

    @staticmethod
    def _render_upload_results(
        web_context: BaseEventAdminWebContext,
    ) -> Template:
        return HTMXTemplate(
            template_name='/chess_results_upload_results.html',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': ChessResultsBackgroundUploader.result_id,
                'upload_status_messages': ChessResultsBackgroundUploader.upload_status_messages,
                'chess_results_utils': ChessResultsUtils,
            },
        )

    @get(
        path='/chess-results/chess-results-upload-results/{event_uniq_id:str}',
        name='chess-results-upload-results',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_chess_results_upload_results(
        self, request: HTMXRequest
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_upload_results(web_context)

    @post(
        path='/chess-results/chess-results-upload/{event_uniq_id:str}',
        name='chess-results-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_chess_results_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        ChessResultsBackgroundUploader.upload_event(web_context.get_admin_event())
        return self._render_upload_results(web_context)

    @post(
        path='/chess-results/chess-results-upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='chess-results-upload-tournament',
        guards=[EventGuard(), TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_chess_results_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()

        ChessResultsBackgroundUploader.schedule_upload(tournament, True)

        return self._render_upload_results(web_context)
