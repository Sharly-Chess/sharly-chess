import json
import time
from abc import ABC, abstractmethod
from functools import cached_property
from logging import Logger
from typing import Any

from httpdate.httpdate import unixtime_to_httpdate
from litestar.datastructures import CacheControlHeader
from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.columns.board_table import BoardColumn
from data.columns.player_table import TournamentPlayerTableColumn
from data.screens.display_controller import DisplayController
from data.screens.family import Family
from data.screens.menu import Menu
from data.screens.rotator import Rotator
from data.screens.screen import Screen
from web.controllers.user.base_user_controller import BaseUserController
from web.controllers.user.event_user_controller import (
    EventUserWebContext,
)
from web.messages import Message
from web.session import (
    SessionLastResultUpdated,
    SessionLastIllegalMoveUpdated,
    SessionLastCheckInUpdated,
)
from web.utils import RequestUtils

logger: Logger = get_logger()


class ScreenEntityUserWebContext(EventUserWebContext, ABC):
    def __init__(
        self,
        request: HTMXRequest,
        user_event_tab: str | None = None,
    ):
        super().__init__(request, user_event_tab=user_event_tab)
        self.rotator: Rotator | None = None
        self.rotator_screen_index: int | None = None
        self.display_controller: DisplayController | None = None
        self.menu: Menu | None = None
        self.is_rotator: bool = False
        # A paged screen opened as a whole, going through its pages.
        self.cycling_family: Family | None = None

    @property
    @abstractmethod
    def screen(self) -> Screen:
        pass

    @cached_property
    def family(self) -> Family | None:
        if ':' in self.screen.uniq_id:
            family_uniq_id: str = self.screen.uniq_id.split(':')[0]
            try:
                return self.user_event.families_by_uniq_id[family_uniq_id]
            except KeyError:
                raise NotFoundException(
                    f'Family [{family_uniq_id}] not found.'
                ) from None
        return None

    @property
    def background_color(self) -> str:
        if self.screen:
            return self.screen.background_color
        if self.rotator:
            return self.rotator.event.background_color
        if self.display_controller:
            return self.display_controller.event.background_color
        return SharlyChessConfig.default_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'rotator': self.rotator,
            'rotator_screen_index': self.rotator_screen_index,
            'is_rotator': self.is_rotator,
            'screen': self.screen,
            'family': self.family,
            'display_controller': self.display_controller,
            'display_controller_query': (
                f'?screen_index={self.rotator_screen_index}'
                if self.display_controller and self.rotator_screen_index
                else ''
            ),
            'menu': self.menu,
            'menu_query': f'?menu_id={self.menu.id}' if self.menu else '',
            'cycling_family': self.cycling_family,
            'cycling_family_delay': (
                self.cycling_family.page_delay
                or SharlyChessConfig.default_rotator_delay
                if self.cycling_family
                else None
            ),
        }


class ScreenUserWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self._screen: Screen = RequestUtils.get_screen(request)
        self.user_event_tab = self.screen.type

    @property
    def screen(self) -> Screen:
        return self._screen


class RotatorUserWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest, rotator_screen_index: int):
        super().__init__(request, user_event_tab='rotators')
        self.rotator = RequestUtils.get_rotator(request)
        self.rotator_screen_index = 0
        self._screen: Screen | None = None
        screens = self.rotator.rotating_screens_for(self.client.remote)
        if screens:
            self.rotator_screen_index = rotator_screen_index % len(screens)
            self._screen = screens[self.rotator_screen_index]
        elif self.client.remote:
            raise NotFoundException(
                f'Rotator [{self.rotator.id}] has no screen served over the internet.'
            )
        self.is_rotator = True

    @property
    def screen(self) -> Screen:
        assert self._screen is not None
        return self._screen


class PagedScreenUserWebContext(ScreenEntityUserWebContext):
    """A paged screen opened as a whole: its pages in turn, at its pace."""

    def __init__(self, request: HTMXRequest, page_index: int):
        super().__init__(request, user_event_tab='screens')
        family = RequestUtils.get_family(request)
        pages = list(family.screens_by_uniq_id.values())
        if not pages:
            raise NotFoundException(f'Paged screen [{family.uniq_id}] has no page.')
        self.cycling_family = family
        self.rotator_screen_index = page_index % len(pages)
        self._screen: Screen = pages[self.rotator_screen_index]
        # A paged screen taking input stays on its page under whoever uses it.
        self.is_rotator = len(pages) > 1 and family.allowed_in_rotators

    @property
    def screen(self) -> Screen:
        return self._screen


class MenuUserWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest, rotator_screen_index: int):
        super().__init__(request, user_event_tab='menus')
        self.menu = RequestUtils.get_menu(request)
        self._screen: Screen | None = None
        self.rotator_screen_index = 0
        screens = self.menu.screens_for(
            self.client.can_view_private_screens, remote=self.client.remote
        )
        if screens:
            self.rotator_screen_index = rotator_screen_index % len(screens)
            self._screen = screens[self.rotator_screen_index]
        elif self.client.remote:
            # A menu waits on the screens it is going to show, which is worth
            # saying on the venue's own network. From the internet there is
            # nothing to wait for: the screens are served elsewhere, and a
            # page that says otherwise promises what will never arrive.
            raise NotFoundException(
                f'Menu [{self.menu.id}] shows no screen served over the internet.'
            )

    @property
    def has_screen(self) -> bool:
        return self._screen is not None

    @property
    def screen(self) -> Screen:
        assert self._screen is not None
        return self._screen


class DisplayControllerUserWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest, rotator_screen_index: int):
        super().__init__(request, user_event_tab='display_controllers')
        self.display_controller = RequestUtils.get_display_controller(request)
        self._screen: Screen | None = None
        self.rotator_screen_index = 0
        self.is_rotator = self.display_controller.cycles
        screens = self.display_controller.screens_for(
            self.client.can_view_private_screens, remote=self.client.remote
        )
        if screens:
            showing = request.query_params.get('showing')
            if showing and showing != self.display_controller.assignment_key:
                rotator_screen_index = 0
            self.rotator_screen_index = rotator_screen_index % len(screens)
            self._screen = screens[self.rotator_screen_index]
        elif self.client.remote:
            raise NotFoundException(
                f'Display controller [{self.display_controller.id}] shows no '
                f'screen served over the internet.'
            )

    @property
    def has_screen(self) -> bool:
        return self._screen is not None

    @property
    def screen(self) -> Screen:
        assert self._screen is not None
        return self._screen


class DisplayControllerWaitingWebContext(EventUserWebContext):
    """A display controller with nothing to show yet."""

    def __init__(self, request: HTMXRequest):
        super().__init__(request, user_event_tab='display_controllers')
        self.display_controller = RequestUtils.get_display_controller(request)

    @property
    def template_context(self) -> dict[str, Any]:
        display_controller = self.display_controller
        event_uniq_id = self.user_event.uniq_id
        return super().template_context | {
            'waiting_name': display_controller.name,
            'waiting_message': _('Connected. Waiting for a screen…'),
            'waiting_icon': 'bi-display',
            'waiting_testid': 'display-controller-waiting',
            'waiting_refresher_class': 'display-controller-refresher',
            'waiting_url': self.request.app.route_reverse(
                'user-display-controller',
                event_uniq_id=event_uniq_id,
                display_controller_id=display_controller.id,
            ),
            'waiting_ws_event': (
                f'ws:display-controller-updated|{event_uniq_id}|{display_controller.id}'
            ),
            'waiting_live_events': None,
            'waiting_delay': display_controller.delay,
        }


class MenuWaitingWebContext(EventUserWebContext):
    """A menu with no screen to show, until it is given one."""

    def __init__(self, request: HTMXRequest):
        super().__init__(request, user_event_tab='menus')
        self.menu = RequestUtils.get_menu(request)

    @property
    def template_context(self) -> dict[str, Any]:
        event_uniq_id = self.user_event.uniq_id
        return super().template_context | {
            'waiting_name': self.menu.name,
            'waiting_message': _('This menu is empty.'),
            'waiting_icon': 'bi-list-nested',
            'waiting_testid': 'menu-waiting',
            'waiting_refresher_class': 'menu-refresher',
            'waiting_url': self.request.app.route_reverse(
                'user-menu', event_uniq_id=event_uniq_id, menu_id=self.menu.id
            ),
            'waiting_ws_event': None,
            'waiting_live_events': f'ws:screens-changed|{event_uniq_id}',
            'waiting_delay': SharlyChessConfig.user_screen_update_delay,
        }


class BaseScreenUserController(BaseUserController):
    # A screen asks the server for its updates itself, so a copy kept by the
    # browser could only show a page out of date or hold its requests back.
    cache_control = CacheControlHeader(no_store=True)

    REFRESH_HEADER: str = 'X-Sharly-Chess-Refresh'
    """Marks the requests a screen makes by itself to stay up to date, which
    leave the messages of the session to the page the user acts on."""

    LIVE_UPDATE_HEADER: str = 'X-Sharly-Chess-Live-Update'
    """Asks, instead of the screen, for the elements of the screen that the
    boards and the players it names bring a change to, as a JSON object with
    the lists ``board_ids`` and ``player_ids``."""

    @staticmethod
    def _live_update_ids(live_update: str, key: str) -> set[int]:
        try:
            ids = json.loads(live_update).get(key, [])
        except ValueError, AttributeError:
            return set()
        return {value for value in ids if isinstance(value, int)}

    @classmethod
    def _user_screen_render(
        cls,
        web_context: ScreenEntityUserWebContext,
        *,
        template_name: str = 'user/screen.html',
        trigger_event: str | None = None,
    ) -> HTMXTemplate:
        columns_by_tournament_id: dict[
            int, list[TournamentPlayerTableColumn] | list[BoardColumn]
        ] = {}
        event = web_context.user_event
        if web_context.screen:
            screen = web_context.screen
            screen_type = screen.screen_type
            for tournament in {
                screen_set.tournament for screen_set in screen.sorted_screen_sets
            }:
                columns = screen_type.build_columns(
                    screen, tournament, event, web_context.client
                )
                if columns is not None:
                    columns_by_tournament_id[tournament.id] = columns
        request = web_context.request
        live_update = request.headers.get(cls.LIVE_UPDATE_HEADER)
        if (
            live_update is not None
            and web_context.screen.screen_type.live_update_template
        ):
            return HTMXTemplate(
                template_name='user/screen/live_update.html',
                context=web_context.template_context
                | {
                    'last_result_updated': SessionLastResultUpdated(request).get(),
                    'last_illegal_move_updated': SessionLastIllegalMoveUpdated(
                        request
                    ).get(),
                    'columns_by_tournament_id': columns_by_tournament_id,
                    'last_check_in_updated': SessionLastCheckInUpdated(request).get(),
                    'live_board_ids': cls._live_update_ids(live_update, 'board_ids'),
                    'live_player_ids': cls._live_update_ids(live_update, 'player_ids'),
                },
            )
        # The page asks to be refreshed once the event changes after the data
        # it shows. A change committed while a refresh is being built is
        # missing from it, so a refresh is dated from when the event was read;
        # a request that writes the event shows its own change, which the time
        # of the reply covers.
        read_since = (
            web_context.user_event.read_at if request.method == 'GET' else time.time()
        )
        return HTMXTemplate(
            template_name=template_name,
            context=web_context.template_context
            | {
                'read_since': read_since,
                'read_since_http_date': unixtime_to_httpdate(int(read_since)),
                'last_result_updated': SessionLastResultUpdated(request).get(),
                'last_illegal_move_updated': SessionLastIllegalMoveUpdated(
                    request
                ).get(),
                'last_check_in_updated': SessionLastCheckInUpdated(request).get(),
                'messages': (
                    []
                    if request.headers.get(cls.REFRESH_HEADER)
                    else Message.messages(request)
                ),
                'columns_by_tournament_id': columns_by_tournament_id,
            },
            trigger_event=trigger_event,
            after='settle' if trigger_event else None,
        )
