from functools import partial
from typing import Any

from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from plugins.chess_results import PLUGIN_NAME
from plugins.chess_results.chess_results_background_uploader import (
    ChessResultsBackgroundUploader,
)
from plugins.chess_results.utils import ChessResultsUtils
from plugins.utils import PluginUtils
from utils.date_time import format_datetime
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import EventGuard, TournamentActionGuard

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessResultsAdminEventController(BaseEventAdminController):
    guards = [EventGuard(), TournamentActionGuard(AuthAction.PUBLISH_RESULTS)]

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.PUBLISH_RESULTS
        )

    @classmethod
    def _upload_results_context(
        cls, web_context: BaseEventAdminWebContext
    ) -> dict[str, Any]:
        return web_context.template_context | {
            'format_datetime': format_datetime,
            'result_id': ChessResultsBackgroundUploader.result_id,
            'upload_status_messages': ChessResultsBackgroundUploader.upload_status_messages,
            'chess_results_utils': ChessResultsUtils,
            'allowed_tournaments': cls._allowed_tournaments(web_context),
        }

    @get(
        path='/chess-results/chess-results-upload-modal/{event_uniq_id:str}',
        name='chess-results-upload-modal',
    )
    async def htmx_admin_chess_results_upload_modal(
        self, request: HTMXRequest
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)

        ChessResultsBackgroundUploader.update_eligible_tournaments(
            self._allowed_tournaments(web_context)
        )

        return HTMXTemplate(
            template_name='/chess_results_upload_modal.html',
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
            context=self._upload_results_context(web_context),
        )

    @classmethod
    def _render_upload_results(
        cls,
        web_context: BaseEventAdminWebContext,
    ) -> Template:
        return HTMXTemplate(
            template_name='/chess_results_upload_results.html',
            context=cls._upload_results_context(web_context),
        )

    @get(
        path='/chess-results/chess-results-upload-results/{event_uniq_id:str}',
        name='chess-results-upload-results',
    )
    async def htmx_admin_chess_results_upload_results(
        self, request: HTMXRequest
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_upload_results(web_context)

    @post(
        path='/chess-results/chess-results-upload/{event_uniq_id:str}',
        name='chess-results-upload',
    )
    async def htmx_admin_chess_results_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        ChessResultsBackgroundUploader.upload_event_tournaments(
            self._allowed_tournaments(web_context)
        )
        return self._render_upload_results(web_context)

    @post(
        path='/chess-results/chess-results-upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='chess-results-upload-tournament',
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
