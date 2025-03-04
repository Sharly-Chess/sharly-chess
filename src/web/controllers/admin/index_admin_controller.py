from logging import Logger
from typing import Annotated, Any

from litestar import get, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect

from common.i18n import _
from common.logger import get_logger
from database.sqlite.event_database import EventDatabase
from database.store import StoredEvent
from web.controllers.admin.base_admin_controller import AdminWebContext, BaseAdminController
from web.messages import Message
from web.urls import admin_event_url

import web.controllers.admin.event_admin_controller as EAC

logger: Logger = get_logger()

class IndexAdminController(BaseAdminController):
    @classmethod
    def _admin(
        cls,
        request: HTMXRequest,
        admin_tab: str | None,
        locale: str | None = None,
        modal: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        cls.set_locale(request, locale)
        web_context: AdminWebContext = AdminWebContext(
            request, data=None, admin_tab=admin_tab
        )
        if web_context.error:
            return web_context.error
        return cls._admin_render(web_context, modal=modal, data=data, errors=errors)

    @get(
        path='/admin',
        name='admin',
        cache=1,
    )
    async def htmx_admin(
        self,
        request: HTMXRequest,
        locale: str | None,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=None,
            locale=locale,
        )

    @get(
        path='/admin/{admin_tab:str}',
        name='admin-tab',
        cache=1,
    )
    async def htmx_admin_tab(
        self,
        request: HTMXRequest,
        admin_tab: str,
        locale: str | None,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=admin_tab,
            locale=locale,
        )

    @get(
        path='/admin/{admin_tab:str}/event-modal/create',
        name='admin-tab-event-create-modal',
        cache=1,
    )
    async def htmx_admin_tab_event_create_modal(
        self,
        request: HTMXRequest,
        admin_tab: str,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=admin_tab,
            modal='event',
        )

    def _admin_event_create(
        self,
        request: HTMXRequest,
        admin_tab: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect | Redirect:
        web_context: AdminWebContext = AdminWebContext(
            request, data=data, admin_tab=admin_tab
        )
        if web_context.error:
            return web_context.error
        stored_event: StoredEvent = self._admin_validate_event_update_data(
            'create', request, None, data
        )
        if stored_event.errors:
            return self._admin(
                request,
                admin_tab=admin_tab,
                modal='event',
                data=data,
                errors=stored_event.errors,
            )
        uniq_id: str = stored_event.uniq_id
        EventDatabase(uniq_id).create()
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            event_database.commit()
        Message.success(
            request, _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id)
        )
        return Redirect(admin_event_url(request, event_uniq_id=uniq_id))

    @post(path='/admin/{admin_tab:str}/create-event', name='admin-tab-create-event')
    async def htmx_admin_tab_event_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        admin_tab: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_create(
            request,
            admin_tab=admin_tab,
            data=data,
        )
