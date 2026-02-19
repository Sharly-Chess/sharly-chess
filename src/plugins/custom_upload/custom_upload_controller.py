from typing import Any, Annotated

from litestar import get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader
from utils.date_time import format_datetime
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard


class CustomUploadAdminEventController(BaseEventAdminController):
    guards = []

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
            'allowed_tournaments': cls._allowed_tournaments(web_context),
        }

    @get(
        path='/custom-upload/modal/{event_uniq_id:str}',
        name='custom-upload-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return HTMXTemplate(
            template_name='/custom_upload_modal.html',
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
            context=self._upload_results_context(web_context),
        )

    @classmethod
    def _render_upload_results(cls, web_context: BaseEventAdminWebContext) -> Template:
        return HTMXTemplate(
            template_name='/custom_upload_results.html',
            context=cls._upload_results_context(web_context),
        )

    @get(
        path='/custom-upload/upload-results/{event_uniq_id:str}',
        name='custom-upload-results',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_results(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/upload/{event_uniq_id:str}',
        name='custom-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)

        # TODO: upload event to custom location

        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-tournament',
        guards=[EventGuard(), TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()

        CustomUploadUploader.schedule_upload(tournament, True)

        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/test-auth',
        name='custom-upload-test-auth',
    )
    async def htmx_custom_upload_test_auth(
        self,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        # TODO: Check if FTP connection is working

        return HTMXTemplate(
            template_name='custom_upload_tournament_auth_fields.html',
            context={
                'data': {
                    'ftp_host': data['ftp_host'],
                    'server_path': data['server_path'],
                    'ftp_username': data['ftp_username'],
                    'ftp_password': data['ftp_password'],
                },
                'ftp_password_visible': data['ftp_password_visible'] == 'true',
                'custom_upload_auth_valid': False,
                'errors': [],
            },
        )
