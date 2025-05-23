from functools import partial
from litestar import post
from litestar.response import Template
from litestar_htmx import HTMXRequest, ClientRedirect

from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_background_uploader import (
    FfeBackgroundUploader,
    FfeUploadResult,
    FfeUploadStatus,
)
from plugins.ffe.ffe_session import FFESession
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.messages import Message

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfeAdminTournamentController(BaseEventAdminController):
    @post(
        path='/ffe/make-visible/{event_uniq_id:str}/tournament/{tournament_id:int}',
        name='ffe-make-visible',
    )
    async def htmx_ffe_make_visible(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context: TournamentAdminWebContext = TournamentAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        admin_event = web_context.admin_event
        assert admin_event is not None
        tournament = web_context.admin_tournament
        assert tournament is not None

        result: FfeUploadResult | None = (
            FfeBackgroundUploader.get_updated_tournament_upload_result(tournament)
        )

        if not NetworkMonitor.connected():
            result = FfeUploadResult(FfeUploadStatus.ERROR, _('No internet connection'))

        def report(
            tournament: Tournament, status: FfeUploadStatus, message: str
        ) -> None:
            nonlocal result
            result = FfeUploadResult(status, message)

        if not result or (
            result.status != FfeUploadStatus.SETTINGS_ERROR
            and result.status != FfeUploadStatus.ERROR
        ):
            try:
                FFESession(
                    tournament,
                    debug=False,
                    report_error=partial(report, tournament, FfeUploadStatus.ERROR),
                    report_info=partial(report, tournament, FfeUploadStatus.INFO),
                    report_success=partial(report, tournament, FfeUploadStatus.SUCCESS),
                ).upload(set_visible=True)
            except Exception:
                logger.exception(
                    'Error while setting tournament visibility: %s', tournament_id
                )
                result = FfeUploadResult(
                    FfeUploadStatus.ERROR, _('Unable to set tournament visibility')
                )

        if result:
            match result.status:
                case FfeUploadStatus.ERROR:
                    Message.error(
                        request,
                        result.message,
                    )
                case FfeUploadStatus.INFO:
                    Message.info(
                        request,
                        result.message,
                    )
                case FfeUploadStatus.SUCCESS | FfeUploadStatus.SETTINGS_ERROR:
                    Message.success(
                        request,
                        result.message,
                    )
        else:
            Message.error(
                request,
                _('Unable to set tournament visibility'),
            )

        return self.render_messages(request)
