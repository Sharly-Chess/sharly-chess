from functools import partial

from litestar import post
from litestar.response import Template
from litestar_htmx import HTMXRequest

from common.logger import get_logger
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from plugins.chess_results import _, PLUGIN_NAME
from plugins.chess_results.chess_results_background_uploader import (
    ChessResultsBackgroundUploader,
    ChessResultsUploadResult,
    ChessResultsUploadStatus,
)
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import ActionGuard, EventGuard, TournamentActionGuard
from web.messages import Message

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessResultsAdminTournamentController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_TOURNAMENTS_TAB),
    ]

    @post(
        path='/chess-results/upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='chess-results-upload-single-tournament',
        guards=[TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_chess_results_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()

        result: ChessResultsUploadResult | None = (
            ChessResultsBackgroundUploader.get_updated_tournament_upload_result(
                tournament
            )
        )

        if not NetworkMonitor.connected():
            result = ChessResultsUploadResult(
                ChessResultsUploadStatus.ERROR, _('No internet connection')
            )

        if not result or (
            result.status != ChessResultsUploadStatus.SETTINGS_ERROR
            and result.status != ChessResultsUploadStatus.ERROR
        ):
            result = ChessResultsBackgroundUploader.upload_tournament(
                tournament.event.uniq_id, tournament.id, force=True
            )

        if result:
            match result.status:
                case ChessResultsUploadStatus.ERROR:
                    Message.error(request, result.message)
                case ChessResultsUploadStatus.INFO:
                    Message.info(request, result.message)
                case (
                    ChessResultsUploadStatus.SUCCESS
                    | ChessResultsUploadStatus.SETTINGS_ERROR
                ):
                    Message.success(request, result.message)
        else:
            Message.error(request, _('Unable to upload tournament.'))

        return self.render_messages(request)
