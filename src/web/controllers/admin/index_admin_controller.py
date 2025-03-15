from logging import Logger
from typing import Annotated

from litestar import get, post, patch
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect

from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredConfig
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from web.controllers.admin.base_admin_controller import AdminWebContext, BaseAdminController
from web.messages import Message
from web.session import SessionHandler
from web.urls import admin_event_url

logger: Logger = get_logger()


class IndexAdminController(BaseAdminController):
    @classmethod
    def _admin(
        cls,
        request: HTMXRequest,
        admin_tab: str | None,
        modal: str | None = None,
        admin_events_show_details: bool | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: AdminWebContext = AdminWebContext(
            request, data=None, admin_tab=admin_tab
        )
        if web_context.error:
            return web_context.error
        if admin_events_show_details is not None:
            SessionHandler.set_session_admin_events_show_details(
                request, admin_events_show_details
            )
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
        admin_events_show_details: bool | None,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=None,
            admin_events_show_details=admin_events_show_details,
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
        admin_events_show_details: bool | None,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=admin_tab,
            admin_events_show_details=admin_events_show_details,
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

    @patch(
        path='/admin/config-update',
        name='admin-config-update',
        cache=1,
    )
    async def htmx_admin_config_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context: AdminWebContext = AdminWebContext(
            request,
            admin_tab='config',
            data=data,
        )
        if web_context.error:
            return web_context.error
        stored_config: StoredConfig = self._admin_validate_config_update_data(data)
        if stored_config.errors:
            return self._admin_render(
                web_context,
                modal='config',
                data=data,
                errors=stored_config.errors,
            )
        with ConfigDatabase(write=True) as config_database:
            stored_config.force_edit = False
            config_database.update_stored_config(stored_config)
            config_database.commit()
            PapiWebConfig().reload()
            Message.success(request, _('Papi-web settings has been updated.'))
        return self._admin_render(
            AdminWebContext(request, data=None, admin_tab='config')
        )

    @get(
        path='/admin/config-modal',
        name='admin-config-modal',
        cache=1,
    )
    async def htmx_admin_config_modal(
        self,
        request: HTMXRequest,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab='config',
            modal='config',
        )
