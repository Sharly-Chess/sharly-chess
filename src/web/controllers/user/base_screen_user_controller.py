from abc import ABC, abstractmethod
from functools import cached_property
from logging import Logger
from typing import Any

from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate

from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.columns.board_table import BoardColumn, ScreenResultColumn
from data.columns.player_table import TournamentPlayerTableColumn, ColumnUsage
from data.columns.handlers import PlayerColumnHandler, BoardColumnHandler
from data.display_controller import DisplayController
from data.family import Family
from data.rotator import Rotator
from data.screen import Screen
from utils.enum import ScreenType
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
        self.is_rotator: bool = False

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
                raise NotFoundException(f'Family [{family_uniq_id}] not found.')
        return None

    @property
    def background_image(self) -> str | None:
        if self.screen:
            return self.screen.background_image
        return None

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
            'is_rotator': self.is_rotator,
            'screen': self.screen,
            'family': self.family,
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


class BaseScreenUserController(BaseUserController):
    @classmethod
    def _user_screen_render(
        cls, web_context: ScreenEntityUserWebContext
    ) -> HTMXTemplate:
        columns_by_tournament_id: dict[
            int, list[TournamentPlayerTableColumn] | list[BoardColumn]
        ] = {}
        event = web_context.user_event
        if web_context.screen:
            screen = web_context.screen
            for tournament in {
                screen_set.tournament for screen_set in screen.sorted_screen_sets
            }:
                if screen.type != ScreenType.RANKING:
                    tournament.set_for_round()
                if screen.type == ScreenType.RANKING:
                    ranking_round = tournament.correct_ranking_round(
                        screen.ranking_round
                    )
                    tournament.compute_tournament_player_ranks(
                        after_round=ranking_round
                    )
                    column_handler = PlayerColumnHandler(event, ColumnUsage.SCREEN)
                    if screen.ranking_crosstable:
                        columns = column_handler.get_player_crosstable_columns(
                            tournament, ranking_round
                        )
                    else:
                        columns = column_handler.get_player_ranking_columns(tournament)
                    columns_by_tournament_id[tournament.id] = columns
                elif screen.type in (ScreenType.BOARDS, ScreenType.INPUT):
                    if tournament.current_round == 0:
                        continue
                    columns_by_tournament_id[tournament.id] = BoardColumnHandler(
                        ColumnUsage.SCREEN
                    ).get_pairings_columns(
                        tournament,
                        tournament.current_round,
                        ScreenResultColumn,
                        show_illegal_moves=(
                            screen.type == ScreenType.INPUT
                            and tournament.record_illegal_moves > 0
                        ),
                    )
        request = web_context.request
        return HTMXTemplate(
            template_name='user/screen.html',
            context=web_context.template_context
            | {
                'last_result_updated': SessionLastResultUpdated(request).get(),
                'last_illegal_move_updated': SessionLastIllegalMoveUpdated(
                    request
                ).get(),
                'last_check_in_updated': SessionLastCheckInUpdated(request).get(),
                'messages': Message.messages(request),
                'columns_by_tournament_id': columns_by_tournament_id,
            },
        )
