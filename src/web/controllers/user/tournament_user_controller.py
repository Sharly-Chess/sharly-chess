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
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils.enum import Result
from web.controllers.admin.pairings_admin_controller import PairingsAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.user.base_screen_user_controller import (
    ScreenUserWebContext,
    BaseScreenUserController,
    BasicScreenOrFamilyUserWebContext,
)
from web.guards import (
    EventGuard,
    ViewScreenGuard,
    TournamentActionGuard,
    SetResultGuard,
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


class TournamentUserWebContext(ScreenUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.tournament: Tournament = RequestUtils.get_tournament(request)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'tournament': self.tournament,
        }


class BoardUserWebContext(TournamentUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.board: Board = RequestUtils.get_board(request)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'board': self.board,
        }


class ResultUserWebContext(BoardUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.board = RequestUtils.get_board(request)
        self.round = self.board.round
        self.result = RequestUtils.get_result(request)


class PlayerUserWebContext(TournamentUserWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.tournament_player: TournamentPlayer = RequestUtils.get_tournament_player(
            request
        )
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


class BaseInputUserController(BaseScreenUserController):
    guards = [
        EventGuard(),
        ViewScreenGuard(),
    ]


class CheckInUserController(BaseInputUserController):
    @get(
        path='/view/checkin-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-checkin-modal',
    )
    async def htmx_user_checkin_modal(self, request: HTMXRequest) -> Template:
        web_context: PlayerUserWebContext = PlayerUserWebContext(
            request,
        )
        return HTMXTemplate(
            template_name='user/modals/check_in_modal.html',
            context=web_context.template_context,
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @patch(
        path='/view/toggle-check-in/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
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
        return self._user_screen_render(BasicScreenOrFamilyUserWebContext(request))


class IllegalMoveUserController(BaseInputUserController):
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
        return self._user_screen_render(BasicScreenOrFamilyUserWebContext(request))

    @put(
        path='/view/add-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-add-illegal-move',
        guards=[TournamentActionGuard(AuthAction.SET_ILLEGAL_MOVES)],
        status_code=HTTP_200_OK,
    )
    async def htmx_user_add_illegal_move(self, request: HTMXRequest) -> Template:
        return self._delete_or_add_illegal_move(request, add=True)

    @delete(
        path='/view/delete-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-delete-illegal-move',
        guards=[TournamentActionGuard(AuthAction.SET_ILLEGAL_MOVES)],
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_illegal_move(self, request: HTMXRequest) -> Template:
        return self._delete_or_add_illegal_move(request, add=False)


class ResultUserController(BaseInputUserController):
    @get(
        path='/view/result-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{board_id:int}',
        name='user-result-modal',
        guards=[TournamentActionGuard(AuthAction.ENTER_RESULTS)],
    )
    async def htmx_user_result_modal(self, request: HTMXRequest) -> Template:
        web_context = BoardUserWebContext(request)
        return HTMXTemplate(
            template_name='user/modals/results_modal.html',
            context=web_context.template_context,
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    def _user_update_result(
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
                board_id=board.id,
                expiration=time.time() + 20,
            )
        )
        return self._user_screen_render(BasicScreenOrFamilyUserWebContext(request))

    @put(
        path='/view/add-result/{event_uniq_id:str}/{screen_uniq_id:str}/'
        '{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        name='user-add-result',
        guards=[SetResultGuard()],
    )
    async def htmx_user_add_result(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
    ) -> Template:
        return self._user_update_result(request, channels=channels)

    @delete(
        path='/view/delete-result/{event_uniq_id:str}/{screen_uniq_id:str}/'
        '{tournament_id:int}/{round:int}/{board_id:int}',
        name='user-delete-result',
        guards=[TournamentActionGuard(AuthAction.UPDATE_RESULTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_result(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
    ) -> Template:
        return self._user_update_result(request, channels=channels)
