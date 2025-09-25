from contextlib import suppress

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
    BasicScreenOrFamilyUserWebContext,
    DisplayControllerUserWebContext,
    RotatorUserWebContext,
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
        date: float,
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
            case ScreenType.PLAYERS:
                pass
            case _:
                raise ValueError(f'type={screen_set.type}')
        return False

    @classmethod
    def _user_screen_refresh_needed(
        cls,
        web_context: BasicScreenOrFamilyUserWebContext
        | DisplayControllerUserWebContext,
        date: float,
    ) -> bool:
        if web_context.screen:
            assert web_context.screen.event is not None
            if web_context.screen.event.last_update > date:
                return True
            if web_context.screen.last_update > date:
                return True
            match web_context.screen.type:
                case ScreenType.IMAGE:
                    pass
                case (
                    ScreenType.BOARDS
                    | ScreenType.INPUT
                    | ScreenType.PLAYERS
                    | ScreenType.RANKING
                ):
                    for screen_set in web_context.screen.screen_sets_by_id.values():
                        if cls._user_screen_set_refresh_needed(screen_set, date):
                            return True
                case ScreenType.RESULTS:
                    assert web_context.screen.event is not None
                    results_tournament_ids: list[int] = (
                        web_context.screen.results_tournament_ids
                        if web_context.screen.results_tournament_ids
                        else list(web_context.screen.event.tournaments_by_id.keys())
                    )
                    for tournament_id in results_tournament_ids:
                        with suppress(KeyError):
                            tournament: Tournament = (
                                web_context.screen.event.tournaments_by_id[
                                    tournament_id
                                ]
                            )
                            if (
                                max(
                                    tournament.last_update,
                                    tournament.last_pairing_update,
                                )
                                > date
                            ):
                                return True
                case _:
                    raise ValueError(f'type={web_context.screen.type}')
        elif isinstance(web_context, BasicScreenOrFamilyUserWebContext):
            assert web_context.family is not None
            assert web_context.family.event is not None
            if (
                max(
                    web_context.family.event.last_update,
                    web_context.family.last_update or 0,
                )
                > date
            ):
                return True
        return False

    @get(
        path='/user/screen/{event_uniq_id:str}/{screen_uniq_id:str}',
        name='user-screen',
        guards=[ViewScreenGuard()],
    )
    async def htmx_user_screen(
        self,
        request: HTMXRequest,
    ) -> HTMXTemplate | Reswap:
        web_context = BasicScreenOrFamilyUserWebContext(request)
        date: float | None = self.get_if_modified_since(request)
        if date is None or self._user_screen_refresh_needed(web_context, date):
            return self._user_screen_render(web_context)
        else:
            return Reswap(
                content=None, method='none', status_code=HTTP_304_NOT_MODIFIED
            )

    @head(
        path='/user/screen/{event_uniq_id:str}/{screen_uniq_id:str}',
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
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}',
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}',
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
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}',
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}',
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
            '/user/display-controller/{event_uniq_id:str}/{display_controller_id:int}/{rotator_screen_index:int}',
            '/user/display-controller/{event_uniq_id:str}/{display_controller_id:int}',
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
            '/user/display-controller/{event_uniq_id:str}/{display_controller_id:int}/{rotator_screen_index:int}',
            '/user/display-controller/{event_uniq_id:str}/{display_controller_id:int}',
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
