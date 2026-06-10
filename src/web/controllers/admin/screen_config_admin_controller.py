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


class ScreenConfigAdminController(BaseEventAdminController):
    guards = [EventGuard(), ActionGuard(AuthAction.MANAGE_SCREENS)]

    @classmethod
    def _prepare_modal_data(
        cls,
        request: HTMXRequest,
        admin_event: Event,
    ) -> dict[str, Any]:
        stored_event = admin_event.stored_event
        return WebContext.values_dict_to_form_data(
            {
                'background_color': admin_event.background_color,
                'message_text': stored_event.message_text,
                'message_color': admin_event.message_color,
                'message_background_color': admin_event.message_background_color,
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

        message_color: str | None = None
        message_background_color: str | None = None

        background_color = cls._admin_validate_background_color_update_data(
            data, errors
        )
        field = 'message_text'
        message_text = WebContext.form_data_to_str(data, field)
        field = 'message_color'
        if not WebContext.form_data_to_bool(data, field + '_checkbox'):
            try:
                message_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _(
                    'Invalid color [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})
        field = 'message_background_color'
        if not WebContext.form_data_to_bool(data, field + '_checkbox'):
            try:
                message_background_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _(
                    'Invalid color [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})

        if errors:
            return None, errors

        stored_event = replace(
            admin_event.stored_event,
            background_color=background_color,
            message_text=message_text,
            message_color=message_color,
            message_background_color=message_background_color,
        )
        return stored_event, errors

    def _modal_context(
        self,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            'modal': 'screens_config',
            'data': data,
            'errors': errors or {},
        }

    @get(
        path='/screen-config-modal/{event_uniq_id:str}',
        name='admin-screen-config-modal',
    )
    async def htmx_admin_screen_config_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        data = self._prepare_modal_data(request, web_context.get_admin_event())
        template_context = self._modal_context(
            data,
        )

        return self._admin_base_event_render(
            web_context.template_context | template_context,
        )

    @patch(
        path='/screen-update-config/{event_uniq_id:str}',
        name='admin-screen-update-config',
        guards=[ActionGuard(AuthAction.UPDATE_EVENT)],
    )
    async def htmx_admin_event_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        stored_event, errors = self._read_form_data(web_context.get_admin_event(), data)
        if not stored_event:
            template_context = self._modal_context(data, errors=errors)
            return self._admin_base_event_render(
                web_context.template_context | template_context,
            )

        uniq_id = stored_event.uniq_id
        with EventDatabase(uniq_id, write=True) as database:
            database.update_stored_event(stored_event)

        Message.success(
            request,
            _('Screen configuration has been updated.').format(uniq_id=uniq_id),
        )
        return self._render_empty_modal_and_messages(request)
