from typing import Any

from litestar import get
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from litestar_htmx import HTMXRequest

from data.screens.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from plugins.chess960 import PLUGIN_NAME
from plugins.chess960.utils import (
    Chess960ScreenPluginData,
)
from web.controllers.admin.base_admin_controller import AdminWebContext
from web.controllers.admin.screen_admin_controller import (
    ScreenAdminRenderer,
)


class Chess960WebContext(AdminWebContext):
    def __init__(self, request: HTMXRequest, screen_uniq_id: str):
        super().__init__(request)
        self.event = self.get_admin_event()
        self.screen_uniq_id = screen_uniq_id
        screen = self.event.screens_by_uniq_id.get(screen_uniq_id)
        if screen is None or screen.stored_screen is None:
            raise NotFoundException(f'Screen [{screen_uniq_id}] not found.')
        self.screen: Screen = screen

    def load_data(self) -> Chess960ScreenPluginData:
        assert self.screen.stored_screen is not None
        data = Chess960ScreenPluginData.from_stored_value(
            self.screen.stored_screen.plugin_data.get(PLUGIN_NAME, {})
        )
        return data

    def save_data(self, data: Chess960ScreenPluginData) -> None:
        assert self.screen.stored_screen is not None
        self.screen.stored_screen.plugin_data[PLUGIN_NAME] = data.to_stored_value()
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.update_stored_screen(self.screen.stored_screen)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'chess960_screen': self.screen,
            'chess960_screen_uniq_id': self.screen_uniq_id,
        }


class Chess960Controller(ScreenAdminRenderer):
    @get(
        path='/event/{event_uniq_id:str}/chess960-screens',
        name='admin-event-chess960-screens-tab',
    )
    async def htmx_admin_event_chess960_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='chess960')


"""
class Chess960Controller(BaseEventAdminController):
    guards = [EventGuard(), ActionGuard(AuthAction.VIEW_PUBLIC_SCREENS)]

    @classmethod
    def _render_form(
        cls,
        web_context: Chess960WebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> HTMXTemplate:
        template_context = web_context.template_context | {
            'data': data,
            'errors': errors or {},
        }
        return cls._render_modal('/chess960_modal.html', template_context)

    @get(path='/chess960/modal/{event_uniq_id:str}', name='chess960-modal')
    async def htmx_chess960_modal(
        self,
        request: HTMXRequest,
        screen_uniq_id: str,
    ) -> Template:
        web_context = Chess960WebContext(request, screen_uniq_id)
        return self._render_form(web_context)

    @post(path='/chess960/randomize/{event_uniq_id:str}', name='chess960-randomize')
    async def htmx_chess960_randomize(
        self,
        request: HTMXRequest,
        screen_uniq_id: str,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        web_context = Chess960WebContext(request, screen_uniq_id)
        data = dict(data)
        data['chess960_number'] = str(random_position_number())
        return self._render_form(web_context, data=data)
"""
