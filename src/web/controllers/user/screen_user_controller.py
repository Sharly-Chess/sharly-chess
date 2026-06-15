from contextlib import suppress
from datetime import datetime

from litestar import head, get
from litestar.plugins.htmx import HTMXRequest, Reswap
from litestar.response import Template
from litestar.status_codes import HTTP_304_NOT_MODIFIED
from litestar_htmx import HTMXTemplate

from data.screen_set import ScreenSet
from data.tournament import Tournament
from utils.enum import ScreenType
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

    @staticmethod
    def _user_screen_set_refresh_needed(
        screen_set: ScreenSet,
        date: datetime,
    ) -> bool:
        tournament: Tournament = screen_set.tournament
        if (
            max(
                tournament.last_update,
                tournament.last_player_update,
            )
            > date
        ):
            return True
        match screen_set.type:
            case ScreenType.BOARDS | ScreenType.INPUT | ScreenType.RANKING:
                if tournament.last_pairing_update > date:
                    return True
            case ScreenType.PLAYERS | ScreenType.CHECK_IN:
                pass
            case _:
                raise ValueError(f'type={screen_set.type}')
        return False

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
            match screen.type:
                case ScreenType.IMAGE:
                    pass
                case (
                    ScreenType.BOARDS
                    | ScreenType.INPUT
                    | ScreenType.PLAYERS
                    | ScreenType.RANKING
                    | ScreenType.CHECK_IN
                ):
                    for screen_set in screen.screen_sets:
                        if cls._user_screen_set_refresh_needed(screen_set, date_dt):
                            return True
                case ScreenType.RESULTS:
                    results_tournament_ids: list[int] = (
                        screen.results_tournament_ids
                        if screen.results_tournament_ids
                        else list(event.tournaments_by_id.keys())
                    )
                    for tournament_id in results_tournament_ids:
                        with suppress(KeyError):
                            tournament = event.tournaments_by_id[tournament_id]
                            if (
                                max(
                                    tournament.last_update,
                                    tournament.last_pairing_update,
                                )
                                > date_dt
                            ):
                                return True
                case _:
                    raise ValueError(f'type={screen.type}')
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
