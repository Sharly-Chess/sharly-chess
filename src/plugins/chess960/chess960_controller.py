from contextlib import suppress
from typing import Any

from litestar import get, Response
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from litestar_htmx import HTMXRequest

from data.screens.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from plugins.chess960 import PLUGIN_NAME
from plugins.chess960.utils import (
    Chess960ScreenPluginData,
    board_svg,
)
from web.controllers.admin.base_admin_controller import AdminWebContext
from web.controllers.admin.screen_admin_controller import (
    ScreenAdminRenderer,
)
from web.controllers.base_controller import BaseController


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
    async def admin_event_chess960_screens_tab(
        self,
        request: HTMXRequest,
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='chess960')


class Chess960SvgController(BaseController):
    @get(
        path='/chess960-svg',
        name='chess960-svg',
    )
    async def chess960_svg(
        self,
        chess960_number: Any = 0,
    ) -> Response[str]:
        number: int = 0
        with suppress(ValueError):
            number = int(chess960_number)
        return Response(content=board_svg(number), media_type='image/svg+xml')
