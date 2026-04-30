from dataclasses import replace
from logging import Logger
from typing import Annotated, Any

from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.event import Event

from litestar import get, patch
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from common.i18n import (
    _,
)

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard
from web.messages import Message

logger: Logger = get_logger()


class PrizeConfigAdminController(BaseEventAdminController):
    guards = [EventGuard(), ActionGuard(AuthAction.MANAGE_PRIZES)]

    @classmethod
    def _prepare_modal_data(
        cls,
        request: HTMXRequest,
        admin_event: Event,
    ) -> dict[str, Any]:
        stored_event = admin_event.stored_event

        return WebContext.values_dict_to_form_data(
            {
                'prize_currency': stored_event.prize_currency,
            }
        )

    @classmethod
    def _read_form_data(
        cls,
        admin_event: Event,
        data: dict[str, str] | None = None,
    ) -> tuple[StoredEvent | None, dict[str, str]]:
        if data is None:
            data = {}
        errors: dict[str, str] = {}

        prize_currency = WebContext.form_data_to_str(data, 'prize_currency')

        if errors:
            return None, errors

        stored_event = replace(
            admin_event.stored_event,
            prize_currency=prize_currency,
        )
        return stored_event, errors

    def _modal_context(
        self,
        event: Event,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            'modal': 'prizes_config',
            'data': data,
            'errors': errors or {},
        }

    @get(
        path='/prize-config-modal/{event_uniq_id:str}',
        name='admin-prize-config-modal',
    )
    async def htmx_admin_prize_config_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        data = self._prepare_modal_data(request, web_context.get_admin_event())
        template_context = self._modal_context(event, data)

        return self._admin_base_event_render(
            web_context.template_context | template_context,
        )

    @patch(
        path='/prize-update-config/{event_uniq_id:str}',
        name='admin-prize-update-config',
        guards=[ActionGuard(AuthAction.UPDATE_EVENT)],
    )
    async def htmx_admin_prize_config_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        stored_event, errors = self._read_form_data(web_context.get_admin_event(), data)
        if not stored_event:
            template_context = self._modal_context(event, data, errors=errors)
            return self._admin_base_event_render(
                web_context.template_context | template_context,
            )

        uniq_id = stored_event.uniq_id
        with EventDatabase(uniq_id, write=True) as database:
            database.update_stored_event(stored_event)

        Message.success(
            request,
            _('Prize defaults have been updated.').format(uniq_id=uniq_id),
        )
        return self._render_empty_modal_and_messages(request)
