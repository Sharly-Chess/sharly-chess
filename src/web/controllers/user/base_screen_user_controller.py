from abc import ABC, abstractmethod
from logging import Logger
from typing import Any, Iterable

from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, ClientRedirect
from litestar.response import Template

from common.logger import get_logger
from data.display_controller import DisplayController
from data.family import Family
from data.rotator import Rotator
from data.screen import Screen
from utils.enum import ScreenType
from plugins.manager import plugin_manager
from plugins.utils import ExtraColumn
from web.controllers.user.event_user_controller import (
    EventUserWebContext,
    EventUserController,
)
from web.messages import Message
from web.session import SessionHandler
from web.utils import RequestUtils

logger: Logger = get_logger()


class ScreenOrRotatorOrDisplayControllerUserWebContext(EventUserWebContext, ABC):
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
    def background_image(self) -> str:
        return self.screen.background_image

    @property
    def background_color(self) -> str:
        return self.screen.background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'rotator': self.rotator,
            'rotator_screen_index': self.rotator_screen_index,
            'screen': self.screen,
            'display_controller': self.display_controller,
        }


class ScreenUserWebContext(ScreenOrRotatorOrDisplayControllerUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
        )
        if self.error:
            return
        self._screen: Screen = RequestUtils.get_screen(request)
        self.user_event_tab = self.screen.type.value

    @property
    def screen(self) -> Screen:
        return self._screen


class RotatorUserWebContext(ScreenOrRotatorOrDisplayControllerUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
            user_event_tab='rotators',
        )
        if self.error:
            return
        self.rotator, self.rotator_screen_index, self._screen = (
            RequestUtils.get_rotator(request)
        )
        self.is_rotator = True

    @property
    def screen(self) -> Screen:
        return self._screen


class DisplayControllerUserWebContext(ScreenOrRotatorOrDisplayControllerUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
            user_event_tab='display_controllers',
        )
        if self.error:
            return
        self.display_controller, self.rotator_screen_index, self._screen = (
            RequestUtils.get_display_controller(request)
        )
        if self.display_controller.rotator:
            self.is_rotator = True

    @property
    def screen(self) -> Screen:
        return self._screen


class BasicScreenOrFamilyUserWebContext(ScreenUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
        )
        self.family: Family | None = None
        if self.error:
            return
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


class BaseScreenUserController(EventUserController):
    @classmethod
    def _user_screen_render(
        cls,
        web_context: ScreenOrRotatorOrDisplayControllerUserWebContext,
    ) -> Template | ClientRedirect:
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
