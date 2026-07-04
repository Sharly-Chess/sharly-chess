import time
from contextlib import suppress
from typing import Any

from litestar import patch, delete, put, get
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar.channels import ChannelsPlugin

from data.access_levels.actions import AuthAction
from data.board import Board
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from utils.enum import Result
from web.controllers.admin.pairings_admin_controller import PairingsAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.user.base_screen_user_controller import (
    BaseScreenUserController,
    ScreenEntityUserWebContext,
)
from web.guards import (
    EventGuard,
    ViewScreenGuard,
    TournamentActionGuard,
    SetResultGuard,
    ViewDisplayControllerGuard,
)
from web.messages import Message
from web.session import (
    SessionLastResultUpdated,
    LastBoardUpdated,
    LastPlayerUpdated,
    SessionLastIllegalMoveUpdated,
    SessionLastCheckInUpdated,
)
from web.utils import RequestUtils


class UserInputWebContext(ScreenEntityUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.tournament = RequestUtils.get_tournament(request)
        self.display_controller = RequestUtils.get_optional_display_controller(request)
        if self.display_controller:
            screen = self.display_controller.screen
            assert screen is not None
            self._screen = screen
        else:
            self._screen = RequestUtils.get_screen(request)

    @property
    def screen(self) -> Screen:
        return self._screen

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'tournament': self.tournament,
        }


class ResultUserWebContext(UserInputWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.board = RequestUtils.get_board(request)
        self.round = self.board.round
        self.result = RequestUtils.get_result(request)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'board': self.board,
        }


class PlayerUserWebContext(UserInputWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.tournament_player = RequestUtils.get_tournament_player(request)
        self.board: Board | None = (
            self.tournament.boards[self.tournament_player.board_id - 1]
            if self.tournament_player.board_id
            else None
        )

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'tournament_player': self.tournament_player,
            'board': self.board,
        }


class TeamUserWebContext(UserInputWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.team = RequestUtils.get_team(request)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'team': self.team,
        }


class InputUserController(BaseScreenUserController):
    """Controller containing all the input endpoints accessed from screens.
    All endpoints have to be accessible from either a screen of a display controller."""

    guards = [
        EventGuard(),
        ViewScreenGuard(),
        ViewDisplayControllerGuard(),
    ]

    @get(
        path=[
            '/view/checkin-modal/{is_screen:int}/{event_uniq_id:str}/'
            '{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
            '/view/checkin-modal/0/{event_uniq_id:str}/'
            '{display_controller_id:int}/{tournament_id:int}/{player_id:int}',
        ],
        name='user-checkin-modal',
    )
    async def htmx_user_checkin_modal(self, request: HTMXRequest) -> Template:
        web_context = PlayerUserWebContext(request)
        return HTMXTemplate(
            template_name='user/modals/check_in_modal.html',
            context=web_context.template_context,
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @patch(
        path=[
            '/view/toggle-check-in/{is_screen:int}/{event_uniq_id:str}/'
            '{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
            '/view/toggle-check-in/0/{event_uniq_id:str}/'
            '{display_controller_id:int}/{tournament_id:int}/{player_id:int}',
        ],
        name='user-toggle-check-in',
        guards=[TournamentActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_user_toggle_check_in(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
    ) -> Template:
        web_context = PlayerUserWebContext(request)
        tournament = web_context.tournament
        player = web_context.tournament_player
        tournament.check_in_player(player, not player.check_in)
        PlayerAdminController.publish_new_checkin(channels, tournament)
        SessionLastCheckInUpdated(request).set(
            LastPlayerUpdated(
                tournament_id=tournament.id,
                player_id=player.id,
                expiration=time.time() + 20,
            )
        )
        return self._user_screen_render(web_context)

    @get(
        path='/view/team-checkin-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{team_id:int}',
        name='user-team-checkin-modal',
    )
    async def htmx_user_team_checkin_modal(self, request: HTMXRequest) -> Template:
        web_context = TeamUserWebContext(request)
        return HTMXTemplate(
            template_name='user/modals/team_check_in_modal.html',
            context=web_context.template_context,
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @patch(
        path='/view/team-toggle-check-in/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{team_id:int}',
        name='user-team-toggle-check-in',
        guards=[TournamentActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_user_team_toggle_check_in(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
    ) -> Template:
        web_context = TeamUserWebContext(request)
        tournament = web_context.tournament
        team = web_context.team
        with EventDatabase(tournament.event.uniq_id, True) as database:
            team.set_check_in(not team.check_in, database)
        PlayerAdminController.publish_new_checkin(channels, tournament)
        return self._user_screen_render(web_context)

    def _delete_or_add_illegal_move(self, request: HTMXRequest, add: bool) -> Template:
        web_context = PlayerUserWebContext(request)
        tournament = web_context.tournament
        player = web_context.tournament_player
        session_handler = SessionLastIllegalMoveUpdated(request)
        last_player_updated = LastPlayerUpdated(
            tournament_id=tournament.id,
            player_id=player.id,
            expiration=time.time() + 20,
        )
        if add:
            tournament.store_illegal_move(player)
            session_handler.set(last_player_updated)
        else:
            if not tournament.delete_illegal_move(player):
                Message.error(
                    request,
                    f'Player [{player.id}] has no illegal move recorded.',
                )
            else:
                session_handler.set(last_player_updated)
        return self._user_screen_render(web_context)

    @put(
        path=[
            '/view/add-illegal-move/{is_screen:int}/{event_uniq_id:str}/'
            '{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
            '/view/add-illegal-move/0/{event_uniq_id:str}/'
            '{display_controller_id:int}/{tournament_id:int}/{player_id:int}',
        ],
        name='user-add-illegal-move',
        guards=[TournamentActionGuard(AuthAction.SET_ILLEGAL_MOVES)],
        status_code=HTTP_200_OK,
    )
    async def htmx_user_add_illegal_move(self, request: HTMXRequest) -> Template:
        return self._delete_or_add_illegal_move(request, add=True)

    @delete(
        path=[
            '/view/delete-illegal-move/{is_screen:int}/{event_uniq_id:str}/'
            '{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
            '/view/delete-illegal-move/0/{event_uniq_id:str}/'
            '{display_controller_id:int}/{tournament_id:int}/{player_id:int}',
        ],
        name='user-delete-illegal-move',
        guards=[TournamentActionGuard(AuthAction.SET_ILLEGAL_MOVES)],
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_illegal_move(self, request: HTMXRequest) -> Template:
        return self._delete_or_add_illegal_move(request, add=False)

    @get(
        path=[
            '/view/result-modal/{is_screen:int}/{event_uniq_id:str}/{screen_uniq_id:str}/'
            '{tournament_id:int}/{board_id:int}',
            '/view/result-modal/0/{event_uniq_id:str}/{display_controller_id:int}/'
            '{tournament_id:int}/{board_id:int}',
        ],
        name='user-result-modal',
        guards=[TournamentActionGuard(AuthAction.ENTER_RESULTS)],
    )
    async def htmx_user_result_modal(self, request: HTMXRequest) -> Template:
        web_context = ResultUserWebContext(request)
        return HTMXTemplate(
            template_name='user/modals/results_modal.html',
            context=web_context.template_context,
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @put(
        path=[
            '/view/update-result/{is_screen:int}/{event_uniq_id:str}/{screen_uniq_id:str}/'
            '{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
            '/view/update-result/0/{event_uniq_id:str}/{display_controller_id:int}/'
            '{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        ],
        name='user-update-result',
        guards=[SetResultGuard()],
    )
    async def htmx_user_update_result(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
    ) -> Template:
        web_context = ResultUserWebContext(request)
        event = web_context.user_event
        tournament = web_context.tournament
        round_ = web_context.round
        board = web_context.board
        result = web_context.result
        if result == Result.NO_RESULT:
            with suppress(ValueError):
                tournament.delete_result(board)
        else:
            tournament.add_result(board, result)
        PairingsAdminController.publish_new_user_results(
            channels, event.uniq_id, tournament.id, round_
        )
        SessionLastResultUpdated(web_context.request).set(
            LastBoardUpdated(
                tournament_id=tournament.id,
                round=round_,
                # DB identifier, not the display id — display ids repeat
                # across team match blocks.
                board_id=board.identifier,
                expiration=time.time() + 20,
            )
        )
        return self._user_screen_render(web_context)
