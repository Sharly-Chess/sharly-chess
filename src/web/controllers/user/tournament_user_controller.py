from contextlib import suppress
from typing import Any

from litestar import patch, delete, put, get
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, ClientRedirect
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar.channels import ChannelsPlugin

from data.board import Board
from data.player import Player
from data.tournament import Tournament
from utils.enum import Result
from web.controllers.admin.pairings_admin_controller import PairingsAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.user.base_screen_user_controller import (
    ScreenUserWebContext,
    BaseScreenUserController,
    BasicScreenOrFamilyUserWebContext,
)
from web.controllers.user.screen_user_controller import ScreenUserController
from web.guards import Guard
from web.messages import Message
from web.session import SessionHandler
from web.utils import RequestUtils


class TournamentUserWebContext(ScreenUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
        )
        if self.error:
            return
        self.tournament: Tournament = RequestUtils.get_tournament(request)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'tournament': self.tournament,
        }


class BoardUserWebContext(TournamentUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
        )
        if self.error:
            return
        self.board: Board = RequestUtils.get_board(request)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'board': self.board,
        }


class ResultUserWebContext(BoardUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
        )
        if self.error:
            return
        self.round, self.board, self.result = RequestUtils.get_round_board_result(
            request
        )


class PlayerUserWebContext(TournamentUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
    ):
        super().__init__(
            request,
        )
        if self.error:
            return
        self.player: Player = RequestUtils.get_player(request)
        self.board: Board | None = (
            self.tournament.boards[self.player.board_id - 1]
            if self.player.board_id
            else None
        )

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'player': self.player,
            'board': self.board,
        }


class BaseInputUserController(BaseScreenUserController):
    pass


class CheckInUserController(BaseInputUserController):
    check_in_guards = ScreenUserController.screen_guards + [
        Guard.tournament_check_in_is_open,
        Guard.client_can_check_in,
    ]

    @get(
        path='/user/checkin-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-checkin-modal',
        guards=check_in_guards,
    )
    async def htmx_user_checkin_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerUserWebContext = PlayerUserWebContext(
            request,
        )
        if web_context.error:
            return web_context.error
        return HTMXTemplate(
            template_name='user/modals.html',
            context=web_context.template_context | {},
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @patch(
        path='/user/toggle-check-in/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-toggle-check-in',
        guards=check_in_guards,
    )
    async def htmx_user_toggle_check_in(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
    ) -> Template | ClientRedirect:
        player_web_context: PlayerUserWebContext = PlayerUserWebContext(
            request,
        )
        if player_web_context.error:
            return player_web_context.error
        assert player_web_context.player.id is not None
        player_web_context.tournament.check_in_player(
            player_web_context.player, not player_web_context.player.check_in
        )
        PlayerAdminController.publish_new_checkin(
            channels, event_uniq_id, player_web_context.player
        )
        SessionHandler.set_session_user_last_check_in_updated(
            request, player_web_context.tournament.id, player_web_context.player.id
        )
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
            )
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)


class IllegalMoveUserController(BaseInputUserController):
    illegal_moves_guards = ScreenUserController.screen_guards + [
        Guard.tournament_is_playing,
        Guard.tournament_record_illegal_moves_is_possible,
        Guard.client_can_set_illegal_moves,
    ]

    def _delete_or_add_illegal_move(
        self,
        request: HTMXRequest,
        add: bool,
    ) -> Template | ClientRedirect:
        player_web_context: PlayerUserWebContext = PlayerUserWebContext(
            request,
        )
        if player_web_context.error:
            return player_web_context.error
        assert player_web_context.player.id is not None

        if add:
            player_web_context.tournament.store_illegal_move(player_web_context.player)
            SessionHandler.set_session_user_last_illegal_move_updated(
                request, player_web_context.tournament.id, player_web_context.player.id
            )
        else:
            if not player_web_context.tournament.delete_illegal_move(
                player_web_context.player
            ):
                Message.error(
                    request,
                    f'Player [{player_web_context.player.id}] has no illegal move recorded.',
                )
            else:
                SessionHandler.set_session_user_last_illegal_move_updated(
                    request,
                    player_web_context.tournament.id,
                    player_web_context.player.id,
                )
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
            )
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)

    @put(
        path='/user/add-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-add-illegal-move',
        guards=illegal_moves_guards,
        status_code=HTTP_200_OK,
    )
    async def htmx_user_add_illegal_move(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._delete_or_add_illegal_move(
            request,
            add=True,
        )

    @delete(
        path='/user/delete-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-delete-illegal-move',
        guards=illegal_moves_guards,
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_illegal_move(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._delete_or_add_illegal_move(
            request,
            add=False,
        )


class ResultUserController(BaseInputUserController):
    results_guards = ScreenUserController.screen_guards + [
        Guard.tournament_is_playing,
        Guard.client_can_enter_results,
    ]

    @get(
        path='/user/result-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{board_id:int}',
        name='user-result-modal',
        guards=results_guards,
    )
    async def htmx_user_result_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        web_context: BoardUserWebContext = BoardUserWebContext(
            request,
        )
        if web_context.error:
            return web_context.error
        return HTMXTemplate(
            template_name='user/modals.html',
            context=web_context.template_context | {},
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    def _user_update_result(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
    ) -> Template | ClientRedirect:
        result_web_context: ResultUserWebContext = ResultUserWebContext(
            request,
        )
        if result_web_context.error:
            return result_web_context.error
        assert result_web_context.board.id is not None
        if result_web_context.result == Result.NO_RESULT:
            with suppress(ValueError):
                result_web_context.tournament.delete_result(result_web_context.board)
        else:
            result_web_context.tournament.add_result(
                result_web_context.board, result_web_context.result
            )
        PairingsAdminController.publish_new_user_results(
            channels,
            result_web_context.user_event.uniq_id,
            result_web_context.tournament.id,
            result_web_context.round,
        )
        SessionHandler.set_session_last_result_updated(
            request,
            result_web_context.tournament.id,
            result_web_context.round,
            result_web_context.board.id,
        )
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
            )
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)

    @put(
        path='/user/add-result/'
        '{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        name='user-add-result',
        guards=results_guards
        + [
            Guard.client_can_add_result,
        ],
    )
    async def htmx_user_add_result(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
        result: int,
    ) -> Template | ClientRedirect:
        return self._user_update_result(
            request,
            channels=channels,
        )

    @delete(
        path='/user/delete-result/'
        '{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='user-delete-result',
        guards=results_guards
        + [
            Guard.client_can_delete_result,
        ],
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_result(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        return self._user_update_result(
            request,
            channels=channels,
        )
