from contextlib import suppress
from typing import Annotated, Any


from litestar import delete, get, put
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from data.loader import EventLoader
from data.board import Board
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from utils.enum import Result
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import BaseController


class PairingsAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        round_: int | None,
        board_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )
        assert self.admin_event is not None
        self.admin_tournament: Tournament | None = None
        if self.error:
            return

        if (
            tournament_id is None
            and len(self.admin_event.tournaments_sorted_by_uniq_id) > 0
        ):
            tournament_id = self.admin_event.tournaments_sorted_by_uniq_id[0].id

        if tournament_id:
            try:
                self.admin_tournament = self.admin_event.tournaments_by_id[
                    tournament_id
                ]
            except KeyError:
                self._redirect_error(f'Tournament [{tournament_id}] not found.')
                return

        self.admin_round = (
            round_
            if round_ is not None
            else self.admin_tournament.current_round
            if self.admin_tournament is not None
            else 0
        )

        self.admin_boards: list[Board] = []
        self.admin_unpaired: list[Player] = []
        if self.admin_tournament is not None:
            if self.admin_round < self.admin_tournament.current_round:
                self.admin_tournament.calculate_points_before_round(
                    before_round=self.admin_round
                )
                self.admin_boards, self.admin_unpaired = (
                    self.admin_tournament.build_boards(self.admin_round)
                )
            else:
                self.admin_boards, self.admin_unpaired = (
                    self.admin_tournament.build_boards()
                )

        self.admin_board: Board | None = None
        if board_id is not None and self.admin_boards is not None:
            self.admin_board = next(
                (b for b in self.admin_boards if b.board_id == board_id), None
            )

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tournament': self.admin_tournament,
        }


class PairingsAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_pairings_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        tournament_id: int | None = None,
        round_: int | None = None,
        board_id: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        admin_event: Event = web_context.admin_event
        admin_tournament: Tournament | None = web_context.admin_tournament
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )

        match modal:
            case None:
                pass
            case 'pairing':
                template_context |= {
                    'modal': modal,
                    'board': web_context.admin_board,
                }

        template_context |= {
            'admin_event_tab': 'admin-event-pairings-tab',
            'admin_event': admin_event,
            'admin_tournament': admin_tournament,
            'admin_tournament_id': web_context.value_to_form_data(admin_tournament.id)
            if admin_tournament
            else None,
            'tournament_options': web_context.get_tournament_options(),
            'admin_round': web_context.admin_round,
            'admin_boards': web_context.admin_boards,
            'admin_unpaired': web_context.admin_unpaired,
        }

        return cls._admin_event_render(template_context)

    @get(
        path=[
            '/admin/event/{event_uniq_id:str}/pairings',
            '/admin/event/{event_uniq_id:str}/pairings/{tournament_id:int}',
            '/admin/event/{event_uniq_id:str}/pairings/{tournament_id:int}/{round:int}',
        ],
        name='admin-event-pairings-tab',
        cache=1,
    )
    async def htmx_admin_pairings_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        round: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @get(
        path=[
            '/admin/event/{event_uniq_id:str}/pairing/{tournament_id:int}/{round:int}/{board_id:int}',
        ],
        name='admin-event-pairing-modal',
    )
    async def htmx_admin_pairings_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            modal='pairing',
        )

    def _admin_update_result(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round_: int,
        board_id: int,
        result: int | None,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_tournament is None:
            raise RuntimeError('admin_tournament not defined')
        if web_context.admin_board is None:
            raise RuntimeError('admin_board not defined')

        if result is None:
            if web_context.admin_round == web_context.admin_tournament.current_round:
                return BaseController.redirect_error(
                    request, "Can't delete result from previous round"
                )
            with suppress(ValueError):
                web_context.admin_tournament.delete_result(web_context.admin_board)
        else:
            if result not in (Result.admin_imputable_results()):
                return BaseController.redirect_error(
                    request, f'Invalid result [{result}].'
                )
            web_context.admin_tournament.add_result(
                web_context.admin_board,
                Result.from_papi_value(result),
                web_context.admin_round,
            )
        EventLoader.get(request=request).clear_cache(web_context.admin_event.uniq_id)
        web_context = PairingsAdminWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
        )
        if web_context.error:
            return web_context.error
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
        )

    @put(
        path='/admin/pairing/add-result/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        name='admin-add-result',
    )
    async def htmx_user_add_result(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
        result: int,
    ) -> Template | ClientRedirect:
        return self._admin_update_result(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=result,
        )

    @delete(
        path='/admin/pairing/delete-result/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='admin-delete-result',
        status_code=HTTP_200_OK,
    )
    async def htmx_user_delete_result(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_update_result(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=None,
        )
