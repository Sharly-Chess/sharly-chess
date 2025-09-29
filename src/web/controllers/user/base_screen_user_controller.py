from abc import ABC, abstractmethod
from logging import Logger
from typing import Any, Iterable

from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate

from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.display_controller import DisplayController
from data.family import Family
from data.rotator import Rotator
from data.screen import Screen
from utils.enum import ScreenType
from plugins.manager import plugin_manager
from plugins.utils import ExtraColumn
from web.controllers.user.base_user_controller import BaseUserController
from web.controllers.user.event_user_controller import (
    EventUserWebContext,
)
from web.messages import Message
from web.session import SessionHandler
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
        self.is_rotator: bool = False

    @property
    @abstractmethod
    def screen(self) -> Screen:
        pass

    @property
    def background_image(self) -> str | None:
        if self.screen:
            return self.screen.background_image
        elif self.rotator:
            return self.rotator.event.background_image
        elif self.display_controller:
            return self.display_controller.event.background_image
        else:
            return SharlyChessConfig.default_background_image

    @property
    def background_color(self) -> str:
        if self.screen:
            return self.screen.background_color
        elif self.rotator:
            return self.rotator.event.background_color
        elif self.display_controller:
            return self.display_controller.event.background_color
        else:
            return SharlyChessConfig.default_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'rotator': self.rotator,
            'rotator_screen_index': self.rotator_screen_index,
            'screen': self.screen,
            'display_controller': self.display_controller,
        }


class ScreenUserWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self._screen: Screen = RequestUtils.get_screen(request)
        self.user_event_tab = self.screen.type.value

    @property
    def screen(self) -> Screen:
        return self._screen


class RotatorUserWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest, rotator_screen_index: int):
        super().__init__(request, user_event_tab='rotators')
        self.rotator = RequestUtils.get_rotator(request)
        self.rotator_screen_index = 0
        self._screen: Screen | None = None
        if self.rotator.rotating_screens:
            self.rotator_screen_index = rotator_screen_index % len(
                self.rotator.rotating_screens
            )
            self._screen = self.rotator.rotating_screens[self.rotator_screen_index]
        self.is_rotator = True

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
        if rotator := self.display_controller.rotator:
            self.is_rotator = True
            if rotator.rotating_screens:
                self.rotator_screen_index = rotator_screen_index % len(
                    rotator.rotating_screens
                )
                self._screen = rotator.rotating_screens[self.rotator_screen_index]
        else:
            self._screen = self.display_controller.screen

    @property
    def screen(self) -> Screen:
        assert self._screen is not None
        return self._screen


class BasicScreenOrFamilyUserWebContext(ScreenUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.family: Family | None = None
        if ':' in self.screen.uniq_id:
            family_uniq_id: str = self.screen.uniq_id.split(':')[0]
            try:
                self.family = self.user_event.families_by_uniq_id[family_uniq_id]
            except KeyError:
                raise NotFoundException(f'Family [{family_uniq_id}] not found.')

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'family': self.family,
        }


class BaseScreenUserController(BaseUserController):
    @classmethod
    def _user_screen_render(
        cls, web_context: ScreenEntityUserWebContext
    ) -> HTMXTemplate:
        # Allow plugin to provide extra columns
        per_plugin_columns: Iterable[Iterable[ExtraColumn]] = []
        if web_context.screen is not None:
            per_plugin_columns: Iterable[Iterable[ExtraColumn]] = (
                plugin_manager.hook.get_extra_screen_columns(
                    screen=web_context.screen.type
                )
            )
        extra_columns: dict[str, list[ExtraColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)
        if web_context.screen:
            for tournament in {
                screen_set.tournament
                for screen_set in web_context.screen.screen_sets_sorted_by_order
            }:
                if web_context.screen.type == ScreenType.RANKING:
                    tournament.compute_player_ranks(
                        after_round=tournament.correct_ranking_round(
                            web_context.screen.ranking_round
                        )
                    )
                else:
                    tournament.set_for_round()
        return HTMXTemplate(
            template_name='user/screen.html',
            context=web_context.template_context
            | {
                'last_result_updated': SessionHandler.get_session_last_result_updated(
                    web_context.request
                ),
                'last_illegal_move_updated': SessionHandler.get_session_user_last_illegal_move_updated(
                    web_context.request
                ),
                'last_check_in_updated': SessionHandler.get_session_user_last_check_in_updated(
                    web_context.request
                ),
                'messages': Message.messages(web_context.request),
                'extra_columns': extra_columns,
            },
        )
