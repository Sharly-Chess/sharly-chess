from datetime import datetime

from litestar import head, get
from litestar.plugins.htmx import HTMXRequest, Reswap
from litestar.response import Template
from litestar.status_codes import HTTP_304_NOT_MODIFIED
from litestar_htmx import HTMXTemplate

from web.controllers.user.base_screen_user_controller import (
    BaseScreenUserController,
    DisplayControllerUserWebContext,
    RotatorUserWebContext,
    ScreenUserWebContext,
    ScreenEntityUserWebContext,
)
from web.guards import (
    EventGuard,
    ViewScreenGuard,
    ViewRotatorGuard,
    ViewDisplayControllerGuard,
)


class ScreenUserController(BaseScreenUserController):
    guards = [EventGuard()]

    @classmethod
    def _user_screen_refresh_needed(
        cls,
        web_context: ScreenEntityUserWebContext,
        date: float,
    ) -> bool:
        date_dt = datetime.fromtimestamp(date)
        screen = web_context.screen
        family = web_context.family
        if family:
            if family.last_update > date_dt:
                return True
        if screen:
            event = screen.event
            if event.last_update > date_dt:
                return True
            if screen.last_update > date_dt:
                return True
            return screen.screen_type.refresh_needed(screen, date_dt)
        return False

    @get(
        path='/view/screen/{event_uniq_id:str}/{screen_uniq_id:str}',
        name='user-screen',
        guards=[ViewScreenGuard()],
    )
    async def htmx_user_screen(
        self,
        request: HTMXRequest,
    ) -> HTMXTemplate | Reswap:
        web_context = ScreenUserWebContext(request)
        date: float | None = self.get_if_modified_since(request)
        if date is None or self._user_screen_refresh_needed(web_context, date):
            return self._user_screen_render(web_context)
        else:
            return Reswap(
                content=None, method='none', status_code=HTTP_304_NOT_MODIFIED
            )

    @head(
        path='/view/screen/{event_uniq_id:str}/{screen_uniq_id:str}',
        name='user-screen-head',
        guards=[ViewScreenGuard()],
        status_code=HTTP_304_NOT_MODIFIED,
    )
    async def htmx_user_screen_head(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
    ) -> None:
        pass

    @get(
        path=[
            '/view/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}',
            '/view/rotator/{event_uniq_id:str}/{rotator_id:int}',
        ],
        name='user-rotator',
        guards=[ViewRotatorGuard()],
    )
    async def htmx_user_rotator(
        self,
        request: HTMXRequest,
        rotator_screen_index: int = 0,
    ) -> Template:
        web_context = RotatorUserWebContext(request, rotator_screen_index)
        return self._user_screen_render(web_context)

    @head(
        path=[
            '/view/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}',
            '/view/rotator/{event_uniq_id:str}/{rotator_id:int}',
        ],
        name='user-rotator-head',
        guards=[ViewRotatorGuard()],
        status_code=HTTP_304_NOT_MODIFIED,
    )
    async def htmx_user_rotator_head(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        rotator_id: int,
        rotator_screen_index: int = 0,
    ) -> None:
        pass

    @get(
        path=[
            '/view/display-controller/{event_uniq_id:str}/{display_controller_id:int}/{rotator_screen_index:int}',
            '/view/display-controller/{event_uniq_id:str}/{display_controller_id:int}',
        ],
        guards=[ViewDisplayControllerGuard()],
        name='user-display-controller',
    )
    async def htmx_user_display_controller(
        self,
        request: HTMXRequest,
        rotator_screen_index: int = 0,
    ) -> Template | Reswap:
        web_context = DisplayControllerUserWebContext(request, rotator_screen_index)
        date: float | None = (
            self.get_if_modified_since(request) if not web_context.is_rotator else None
        )
        if date is None or self._user_screen_refresh_needed(web_context, date):
            return self._user_screen_render(web_context)
        else:
            return Reswap(
                content=None, method='none', status_code=HTTP_304_NOT_MODIFIED
            )

    @head(
        path=[
            '/view/display-controller/{event_uniq_id:str}/{display_controller_id:int}/{rotator_screen_index:int}',
            '/view/display-controller/{event_uniq_id:str}/{display_controller_id:int}',
        ],
        name='user-display-controller-head',
        guards=[ViewDisplayControllerGuard()],
        status_code=HTTP_304_NOT_MODIFIED,
    )
    async def htmx_user_display_controller_head(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        display_controller_id: int,
        rotator_screen_index: int = 0,
    ) -> None:
        pass
