from contextlib import suppress
from typing import Annotated, Any

from litestar import get
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, Reswap, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_304_NOT_MODIFIED

from common.exception import SharlyChessException
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.auth.client import Client
from data.display_controller import DisplayController
from data.event import Event
from data.loader import EventLoader
from data.rotator import Rotator
from data.screen import Screen
from utils.enum import ScreenType
from web.controllers.user.base_user_controller import (
    BaseUserController,
    UserWebContext,
)
from web.messages import Message


class EventUserWebContext(UserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        user_event_tab: str | None,
    ):
        super().__init__(request, data=data, user_tab=None)
        self.user_event: Event | None = None
        self.user_event_tab: str | None = user_event_tab
        if self.error:
            return
        if not event_uniq_id:
            self._redirect_error('Event not set.')
            return
        try:
            self.user_event = EventLoader.get(request=self.request).load_event(
                event_uniq_id
            )
            if self.user_event.public or self.admin_auth:
                self.user_event_tab = user_event_tab
                return
            self._redirect_error(f'Access denied for event [{event_uniq_id}].')
        except SharlyChessException as pwe:
            self._redirect_error(f'Event [{event_uniq_id}] not found: {pwe}.')

    @property
    def client(self) -> Client:
        """Returns the client (account and computer) of the request."""
        return Client(self.request, self.user_event)

    def check_user_tab(self):
        pass

    @property
    def background_image(self) -> str | None:
        return None

    @property
    def background_color(self) -> str:
        return SharlyChessConfig.user_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'user_event_tab': self.user_event_tab,
            'user_event': self.user_event,
        }


class EventUserController(BaseUserController):
    @staticmethod
    def _user_event_render(
        web_context: EventUserWebContext,
    ) -> Template:
        assert web_context.user_event is not None
        input_screens: list[Screen]
        boards_screens: list[Screen]
        players_screens: list[Screen]
        results_screens: list[Screen]
        ranking_screens: list[Screen]
        image_screens: list[Screen]
        rotators: list[Rotator]
        display_controllers: list[DisplayController]
        if web_context.admin_auth:
            input_screens = (
                web_context.user_event.screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.INPUT
                ]
            )
            boards_screens = (
                web_context.user_event.screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.BOARDS
                ]
            )
            players_screens = (
                web_context.user_event.screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.PLAYERS
                ]
            )
            results_screens = (
                web_context.user_event.screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.RESULTS
                ]
            )
            ranking_screens = (
                web_context.user_event.screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.RANKING
                ]
            )
            image_screens = (
                web_context.user_event.screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.IMAGE
                ]
            )
            rotators = web_context.user_event.rotators_sorted_by_uniq_id
            display_controllers = (
                web_context.user_event.display_controllers_sorted_by_uniq_id
            )
        else:
            input_screens = (
                web_context.user_event.public_screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.INPUT
                ]
            )
            boards_screens = (
                web_context.user_event.public_screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.BOARDS
                ]
            )
            players_screens = (
                web_context.user_event.public_screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.PLAYERS
                ]
            )
            results_screens = (
                web_context.user_event.public_screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.RESULTS
                ]
            )
            ranking_screens = (
                web_context.user_event.public_screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.RANKING
                ]
            )
            image_screens = (
                web_context.user_event.public_screens_by_screen_type_sorted_by_uniq_id[
                    ScreenType.IMAGE
                ]
            )
            rotators = web_context.user_event.public_rotators_sorted_by_uniq_id
            display_controllers = (
                web_context.user_event.public_display_controllers_sorted_by_uniq_id
            )
        nav_tabs: dict[str, dict] = {
            'input': {
                'title': _('Results entry ({num})').format(
                    num=len(input_screens) or '-'
                ),
                'screens': input_screens,
                'disabled': not input_screens,
            },
            'boards': {
                'title': _('Pairings by board ({num})').format(
                    num=len(boards_screens) or '-'
                ),
                'screens': boards_screens,
                'disabled': not boards_screens,
            },
            'players': {
                'title': _('Pairings by player ({num})').format(
                    num=len(players_screens) or '-'
                ),
                'screens': players_screens,
                'disabled': not players_screens,
            },
            'results': {
                'title': _('Last results ({num})').format(
                    num=len(results_screens) or '-'
                ),
                'screens': results_screens,
                'disabled': not results_screens,
            },
            'ranking': {
                'title': _('Ranking ({num})').format(num=len(ranking_screens) or '-'),
                'screens': ranking_screens,
                'disabled': not ranking_screens,
            },
            'image': {
                'title': _('Image ({num})').format(num=len(image_screens) or '-'),
                'screens': image_screens,
                'disabled': not image_screens,
            },
            'rotators': {
                'title': _('Rotators ({num})').format(num=len(rotators) or '-'),
                'rotators': rotators,
                'disabled': not rotators,
            },
            'display_controllers': {
                'title': _('Display controllers ({num})').format(
                    num=len(display_controllers) or '-'
                ),
                'display_controllers': display_controllers,
                'disabled': not display_controllers,
            },
        }
        if (
            not web_context.user_event_tab
            or nav_tabs[web_context.user_event_tab]['disabled']
        ):
            web_context.user_event_tab = list(nav_tabs.keys())[0]
        for nav_index in range(len(nav_tabs)):
            if (
                web_context.user_event_tab == list(nav_tabs.keys())[nav_index]
                and nav_tabs[web_context.user_event_tab]['disabled']
            ):
                web_context.user_event_tab = list(nav_tabs.keys())[
                    (nav_index + 1) % len(nav_tabs)
                ]
        return HTMXTemplate(
            template_name='user/event_layout.html',
            context=web_context.template_context
            | {
                'messages': Message.messages(web_context.request),
                'nav_tabs': nav_tabs,
            },
        )

    @staticmethod
    def _user_event_refresh_needed(
        event: Event,
        date: float,
    ) -> bool:
        if event.last_update and event.last_update > date:
            return True
        for screen in event.basic_screens_by_id.values():
            if screen.last_update > date:
                return True
            for screen_set in screen.screen_sets_by_id.values():
                if screen_set.last_update and screen_set.last_update > date:
                    return True
                if screen_set.tournament.last_update > date:
                    return True
                if screen.type in [
                    ScreenType.BOARDS,
                    ScreenType.INPUT,
                    ScreenType.RANKING,
                ]:
                    if screen_set.tournament.last_illegal_move_update > date:
                        return True
                    if screen_set.tournament.last_result_update > date:
                        return True
                    if screen_set.tournament.last_update > date:
                        return True
                if screen_set.tournament.last_check_in_update > date:
                    return True
            if screen.type == ScreenType.RESULTS:
                assert screen.event is not None
                results_tournament_ids: list[int] = (
                    screen.results_tournament_ids
                    if screen.results_tournament_ids
                    else list(event.tournaments_by_id.keys())
                )
                for tournament_id in results_tournament_ids:
                    with suppress(KeyError):
                        if (
                            screen.event.tournaments_by_id[
                                tournament_id
                            ].last_result_update
                            > date
                        ):
                            return True
        for family in event.families_by_id.values():
            if family.last_update and family.last_update > date:
                return True
            if family.tournament.last_update > date:
                return True
            match family.type:
                case ScreenType.BOARDS | ScreenType.INPUT | ScreenType.RANKING:
                    if family.tournament.last_illegal_move_update > date:
                        return True
                    if family.tournament.last_result_update > date:
                        return True
                    if family.tournament.last_check_in_update > date:
                        return True
                case ScreenType.PLAYERS:
                    if family.tournament.last_check_in_update > date:
                        return True
                case _:
                    raise ValueError(f'type={family.type}')
        return False

    def _user_event(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        user_event_tab: str | None,
        locale: str | None,
    ) -> Template | Reswap | ClientRedirect:
        self.set_locale(request, locale)
        web_context: EventUserWebContext = EventUserWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            user_event_tab=user_event_tab,
        )
        if web_context.error:
            return web_context.error
        if web_context.user_event is None:
            raise RuntimeError('user_event not defined')
        date: float | None = self.get_if_modified_since(request)
        if date is None or self._user_event_refresh_needed(
            web_context.user_event, date
        ):
            return self._user_event_render(web_context)
        else:
            return Reswap(
                content=None, method='none', status_code=HTTP_304_NOT_MODIFIED
            )

    @get(
        path='/user/event/{event_uniq_id:str}',
        name='user-event',
    )
    async def htmx_user_event(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        locale: str | None,
    ) -> Template | Reswap | ClientRedirect:
        return self._user_event(
            request, event_uniq_id=event_uniq_id, user_event_tab=None, locale=locale
        )

    @get(
        path='/user/event/{event_uniq_id:str}/{user_event_tab:str}',
        name='user-event-tab',
    )
    async def htmx_user_event_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        user_event_tab: str,
        locale: str | None,
    ) -> Template | Reswap | ClientRedirect:
        return self._user_event(
            request,
            event_uniq_id=event_uniq_id,
            user_event_tab=user_event_tab,
            locale=locale,
        )
