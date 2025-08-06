from functools import partial
from pathlib import Path

from litestar import post, get
from litestar.response import Template, File
from litestar_htmx import HTMXRequest, ClientRedirect

from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
from plugins import ffe
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
        path='/ffe/make-visible/{event_uniq_id:str}/{tournament_id:int}',
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

        def report(status: FfeUploadStatus, message: str) -> None:
            nonlocal result
            result = FfeUploadResult(status, message)

        if not result or (
            result.status != FfeUploadStatus.SETTINGS_ERROR
            and result.status != FfeUploadStatus.ERROR
        ):
            try:
                FFESession(
                    tournament,
                    report_error=partial(report, FfeUploadStatus.ERROR),
                    report_info=partial(report, FfeUploadStatus.INFO),
                    report_success=partial(report, FfeUploadStatus.SUCCESS),
                ).upload(set_visible=True)
            except Exception:
                logger.exception(
                    'Error while setting tournament visibility: %s', tournament_id
                )
                result = FfeUploadResult(
                    FfeUploadStatus.ERROR, _('Unable to set tournament visibility.')
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
                _('Unable to set tournament visibility.'),
            )

        return self.render_messages(request)

    @post(
        path='/ffe/upload-rules/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-upload-rules',
    )
    async def htmx_ffe_upload_rules(
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

        if not tournament.rules:
            result = FfeUploadResult(
                FfeUploadStatus.ERROR, _('Tournament rules are not set')
            )

        def report(status: FfeUploadStatus, message: str) -> None:
            nonlocal result
            result = FfeUploadResult(status, message)

        if not result or (
            result.status != FfeUploadStatus.SETTINGS_ERROR
            and result.status != FfeUploadStatus.ERROR
        ):
            try:
                FFESession(
                    tournament,
                    report_error=partial(report, FfeUploadStatus.ERROR),
                    report_info=partial(report, FfeUploadStatus.INFO),
                    report_success=partial(report, FfeUploadStatus.SUCCESS),
                ).upload_rules()
            except Exception:
                logger.exception(
                    'Error while uploading tournament rules: %s', tournament_id
                )
                result = FfeUploadResult(
                    FfeUploadStatus.ERROR, _('Unable to upload tournament rules.')
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
                _('Unable to upload tournament rules.'),
            )

        return self.render_messages(request)

    @staticmethod
    def tournament_fees_file(
        tournament,
    ) -> Path:
        return (
            ffe.TMP_DIR
            / 'fees'
            / tournament.event.uniq_id
            / f'{tournament.uniq_id}.html'
        )

    @get(
        path='/ffe/extract-fees/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-extract-fees',
    )
    async def htmx_ffe_extract_fees(
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

        def report(status: FfeUploadStatus, message: str) -> None:
            nonlocal result
            result = FfeUploadResult(status, message)

        if not result or (
            result.status != FfeUploadStatus.SETTINGS_ERROR
            and result.status != FfeUploadStatus.ERROR
        ):
            try:
                if html := FFESession(
                    tournament,
                    report_error=partial(report, FfeUploadStatus.ERROR),
                    report_info=partial(report, FfeUploadStatus.INFO),
                    report_success=partial(report, FfeUploadStatus.SUCCESS),
                ).get_fees():
                    fees_file = self.tournament_fees_file(tournament)
                    fees_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(fees_file, 'w') as f:
                        f.write(html)
                    url: str = request.app.route_reverse(
                        'ffe-download-fees',
                        event_uniq_id=event_uniq_id,
                        tournament_id=tournament_id,
                    )
                    logger.debug(
                        'Fees written to [%s], redirecting to [%s].',
                        fees_file,
                        url,
                    )
                    response: ClientRedirect = ClientRedirect(redirect_to=url)
                    # cf https://github.com/bigskysoftware/htmx/issues/3189
                    response.set_header('HX-Trigger', 'download_ready')
                    return response
            except Exception:
                logger.exception('Error while downloading fees: %s', tournament_id)
                result = FfeUploadResult(
                    FfeUploadStatus.ERROR, _('Unable to download tournament fees.')
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
                _('Unable to download tournament fees.'),
            )

        return self.render_messages(request)

    @get(
        path='/ffe/download-fees/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-download-fees',
    )
    async def ffe_download_fees(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect | File:
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

        file: Path = self.tournament_fees_file(tournament)
        return File(
            path=file,
            filename=f'{event_uniq_id}-{tournament.uniq_id}-fees.html',
        )
