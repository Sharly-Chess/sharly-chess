from contextlib import suppress
from io import BytesIO
from logging import Logger
from pathlib import Path
from typing import Annotated, Any
from zipfile import ZipInfo, ZipFile

from litestar import patch, delete, put, Response, get
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from common.logger import get_logger
from data.board import Board
from data.loader import EventLoader
from data.player import Player
from data.tournament import Tournament
from utils.enum import Result
from web.controllers.base_controller import BaseController
from web.controllers.user.event_user_controller import EventUserWebContext
from web.controllers.user.base_user_controller import BaseUserController
from web.controllers.user.base_screen_user_controller import (
    ScreenUserWebContext,
    BaseScreenUserController,
    BasicScreenOrFamilyUserWebContext,
)
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class TournamentUserWebContext(ScreenUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
        event_uniq_id: str,
        screen_uniq_id: str | None,
        screen_needed: bool,
        tournament_id: int,
        tournament_started: bool | None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            screen_needed=screen_needed,
        )
        self.tournament: Tournament | None = None
        if self.error:
            return
        assert self.user_event is not None
        try:
            self.tournament = self.user_event.tournaments_by_id[tournament_id]
        except KeyError:
            self._redirect_error(f'Tournament [{tournament_id}] not found.')
            return
        if tournament_started is not None:
            if tournament_started:
                if not self.tournament.current_round:
                    self._redirect_error(
                        _(
                            'Tournament [{tournament_uniq_id}] is not started yet.'
                        ).format(tournament_uniq_id=self.tournament.uniq_id)
                    )
                    return
            else:
                if self.tournament.current_round:
                    self._redirect_error(
                        _('Tournament [{tournament_uniq_id}] is started.').format(
                            tournament_uniq_id=self.tournament.uniq_id
                        )
                    )
                    return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'tournament': self.tournament,
        }


class BoardUserWebContext(TournamentUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        board_id: int,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            screen_needed=True,
            tournament_id=tournament_id,
            tournament_started=True,
        )
        assert self.tournament is not None
        self.board: Board | None = None
        if self.error:
            return
        try:
            assert self.tournament.boards is not None
            self.board = self.tournament.boards[board_id - 1]
        except KeyError:
            self._redirect_error(f'Board [{board_id}] not found.')
            return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'board': self.board,
        }


class PlayerUserWebContext(TournamentUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
        tournament_started: bool | None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            screen_needed=True,
            tournament_id=tournament_id,
            tournament_started=tournament_started,
        )
        assert self.tournament is not None
        self.player: Player | None = None
        self.board: Board | None = None
        if self.error:
            return
        try:
            self.player = self.tournament.players_by_id[player_id]
        except KeyError:
            self._redirect_error(f'Player [{player_id}] not found.')
            return
        assert self.tournament.boards is not None
        self.board = (
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
    @get(
        path='/user/checkin-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-checkin-modal',
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
            data=None,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            player_id=player_id,
            tournament_started=False,
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
    )
    async def htmx_user_toggle_check_in(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
    ) -> Template | ClientRedirect:
        player_web_context: PlayerUserWebContext = PlayerUserWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            player_id=player_id,
            tournament_started=False,
        )
        if player_web_context.error:
            return player_web_context.error
        assert player_web_context.player is not None
        assert player_web_context.player.id is not None
        assert player_web_context.user_event is not None
        assert player_web_context.tournament is not None
        player_web_context.tournament.check_in_player(
            player_web_context.player, not player_web_context.player.check_in
        )
        SessionHandler.set_session_user_last_check_in_updated(
            request, player_web_context.tournament.id, player_web_context.player.id
        )
        EventLoader.get(request=request).clear_cache(
            player_web_context.user_event.uniq_id
        )
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
                data=None,
                event_uniq_id=event_uniq_id,
                screen_uniq_id=screen_uniq_id,
            )
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)


class IllegalMoveUserController(BaseInputUserController):
    def _delete_or_add_illegal_move(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        player_id: int,
        add: bool,
    ) -> Template | ClientRedirect:
        player_web_context: PlayerUserWebContext = PlayerUserWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            player_id=player_id,
            tournament_started=True,
        )
        if player_web_context.error:
            return player_web_context.error
        assert player_web_context.tournament is not None
        assert player_web_context.player is not None
        assert player_web_context.player.id is not None
        assert player_web_context.user_event is not None

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
        EventLoader.get(request=request).clear_cache(
            player_web_context.user_event.uniq_id
        )
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
                data=None,
                event_uniq_id=event_uniq_id,
                screen_uniq_id=screen_uniq_id,
            )
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)

    @put(
        path='/user/add-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-add-illegal-move',
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
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            player_id=player_id,
            add=True,
        )

    @delete(
        path='/user/delete-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='user-delete-illegal-move',
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
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            player_id=player_id,
            add=False,
        )


class ResultUserController(BaseInputUserController):
    @get(
        path='/user/result-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{board_id:int}',
        name='user-result-modal',
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
            data=None,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            board_id=board_id,
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
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        round_: int,
        board_id: int,
        result: int | None,
    ) -> Template | ClientRedirect:
        board_web_context: BoardUserWebContext = BoardUserWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            board_id=board_id,
        )
        if board_web_context.error:
            return board_web_context.error
        assert board_web_context.tournament is not None
        assert board_web_context.board is not None
        assert board_web_context.board.id is not None
        assert board_web_context.user_event is not None
        if round_ not in range(1, board_web_context.tournament.rounds + 1):
            return BaseController.redirect_error(
                request, f'Invalid round number [{round_}].'
            )
        if result is None:
            if not board_web_context.admin_auth:
                return BaseController.redirect_error(
                    request, 'Result deletion is not allowed.'
                )
            with suppress(ValueError):
                board_web_context.tournament.delete_result(board_web_context.board)
        else:
            if result not in (
                Result.admin_imputable_results()
                if board_web_context.admin_auth
                else Result.user_imputable_results()
            ):
                return BaseController.redirect_error(
                    request, f'Invalid result [{result}].'
                )
            board_web_context.tournament.add_result(
                board_web_context.board, Result.from_papi_value(result)
            )
        SessionHandler.set_session_last_result_updated(
            request, board_web_context.tournament.id, round_, board_web_context.board.id
        )
        EventLoader.get(request=request).clear_cache(
            board_web_context.user_event.uniq_id
        )
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
                data=None,
                event_uniq_id=event_uniq_id,
                screen_uniq_id=screen_uniq_id,
            )
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)

    @put(
        path='/user/add-result/'
        '{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        name='user-add-result',
    )
    async def htmx_user_add_result(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
        result: int,
    ) -> Template | ClientRedirect:
        return self._user_update_result(
            request,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=result,
        )

    @delete(
        path='/user/delete-result/'
        '{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='user-delete-result',
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_result(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        return self._user_update_result(
            request,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=None,
        )


class DownloadUserController(BaseUserController):
    @get(
        path='/user/download-tournaments/{event_uniq_id:str}',
        name='user-download-tournaments',
    )
    async def htmx_user_download_event_tournaments(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Response[bytes] | ClientRedirect:
        web_context: EventUserWebContext = EventUserWebContext(
            request, data=None, event_uniq_id=event_uniq_id, user_event_tab=None
        )
        if web_context.error:
            return web_context.error
        if web_context.user_event is None:
            raise RuntimeError('user_event not defined')
        tournament_files: list[Path] = [
            tournament.file
            for tournament in web_context.user_event.tournaments_by_id.values()
            if tournament.file_exists
        ]
        if not tournament_files:
            return BaseController.redirect_error(
                request, f'No Papi file for event [{web_context.user_event.uniq_id}].'
            )
        archive = BytesIO()
        with ZipFile(archive, 'w') as zip_archive:
            for tournament_file in tournament_files:
                zip_entry: ZipInfo = ZipInfo(tournament_file.name)
                with open(tournament_file, 'rb') as tournament_handler:
                    zip_archive.writestr(zip_entry, tournament_handler.read())
        return Response(
            content=bytes(archive.getbuffer()), media_type='application/zip'
        )

    @get(
        path='/user/download-tournament/{event_uniq_id:str}/{tournament_id:str}',
        name='user-download-tournament',
    )
    async def htmx_user_download_tournament(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> File | ClientRedirect:
        web_context: TournamentUserWebContext = TournamentUserWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=None,
            screen_needed=False,
            tournament_id=tournament_id,
            tournament_started=None,
        )
        if web_context.error:
            return web_context.error
        if web_context.tournament is None:
            raise RuntimeError('tournament not defined')
        if not web_context.tournament.file_exists:
            return BaseController.redirect_error(
                request, f'Papi file [{web_context.tournament.file}] not found.'
            )
        return File(
            path=web_context.tournament.file, filename=web_context.tournament.file.name
        )
