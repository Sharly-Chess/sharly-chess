from typing import Any

from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from utils.date_time import format_timestamp_date_time
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.guards import EventGuard, ActionGuard


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
            'format_timestamp_date_time': format_timestamp_date_time,
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

    @post(
        path='/custom-upload/upload/{event_uniq_id:str}',
        name='custom-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        # TODO: upload to custom location
        return self._render_upload_results(web_context)
