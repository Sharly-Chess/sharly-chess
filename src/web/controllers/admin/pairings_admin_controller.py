from contextlib import suppress
from typing import Annotated, Any


from litestar import delete, get, patch, put, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from data.loader import EventLoader
from data.board import Board
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from pairing.bbp_pairings import BbpPairings
from utils.enum import Result
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import BaseController
from web.messages import Message


class PairingsAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        round_: int | None,
        board_id: int | None,
        player_id: int | None,
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

        self.admin_unpaired = sorted(self.admin_unpaired, key=lambda p: p.last_name)
        self.admin_board: Board | None = None
        if board_id is not None and self.admin_boards is not None:
            self.admin_board = next(
                (b for b in self.admin_boards if b.board_id == board_id), None
            )

        self.admin_player: Player | None = None
        if player_id is not None and self.admin_unpaired is not None:
            self.admin_player = next(
                (p for p in self.admin_unpaired if p.id == player_id), None
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
        player_id: int | None = None,
        data: dict[str, str] | None = None,
        trigger_event: str | None = None,
        full_refresh: bool = False,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            player_id=player_id,
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
            case 'unpaired-player':
                print(
                    web_context.admin_round,
                    web_context.admin_tournament.rounds,
                    web_context.admin_tournament.last_rounds_no_byes,
                )
                if (
                    web_context.admin_player is not None
                    and web_context.admin_tournament is not None
                ):
                    byes: int = 0
                    for round_ in web_context.admin_player.pairings:
                        match web_context.admin_player.pairings[round_].result:
                            case Result.HALF_POINT_BYE:
                                byes += 1
                            case Result.FULL_POINT_BYE:
                                byes += 2

                    template_context |= {
                        'modal': modal,
                        'player': web_context.admin_player,
                        'exempt_player': next(
                            (
                                b.white_player
                                for b in web_context.admin_boards
                                if b.exempt
                            ),
                            None,
                        ),
                        'hpb_possible': byes < web_context.admin_tournament.max_byes,
                    }
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
            'board': web_context.admin_board,
            'wp': web_context.admin_board.white_player
            if web_context.admin_board
            else None,
            'bp': web_context.admin_board.black_player
            if web_context.admin_board
            else None,
        }

        if not full_refresh and web_context.admin_board is not None and modal is None:
            board_id = web_context.admin_board.board_id
            assert board_id is not None
            next_board_id = next(
                (
                    b.board_id
                    for b in web_context.admin_boards
                    if b.board_id is not None and b.board_id > board_id
                ),
                None,
            )

            return HTMXTemplate(
                template_name='/admin/pairings/pairing_row.html',
                context=template_context,
                re_target=f'[data-board-id="{web_context.admin_board.board_id}"]',
                re_swap='outerHTML',
                trigger_event=trigger_event,
                after='receive',
                params={
                    'board_id': next_board_id,
                },
            )
        else:
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

    @get(
        path=[
            '/admin/event/{event_uniq_id:str}/unpaired-modal/{tournament_id:int}/{round:int}/{player_id:int}',
        ],
        name='admin-event-unpaired-player-modal',
    )
    async def htmx_admin_unpaired_player_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            player_id=player_id,
            modal='unpaired-player',
        )

    def _admin_update_result(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round_: int,
        board_id: int,
        result: int | None,
        trigger_event: str | None = None,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            player_id=None,
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

        if web_context.admin_board.exempt:
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round_,
            )

        can_pair = web_context.admin_tournament.pairings_generation_allowed
        if result is None:
            if web_context.admin_round < web_context.admin_tournament.current_round:
                Message.error(
                    request,
                    _("Can't delete result from previous round"),
                )
                return self._admin_event_pairings_render(
                    request,
                    event_uniq_id=event_uniq_id,
                    tournament_id=tournament_id,
                    round_=round_,
                    board_id=board_id,
                    modal='pairing',
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
            player_id=None,
        )
        if web_context.error:
            return web_context.error
        assert web_context.admin_tournament is not None
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            trigger_event=trigger_event,
            full_refresh=can_pair
            != web_context.admin_tournament.pairings_generation_allowed,
        )

    @put(
        path='/admin/pairing/set-result/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        name='admin-set-result',
    )
    async def htmx_admin_set_result(
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
            trigger_event='close_modal',
        )

    @delete(
        path='/admin/pairing/unpair/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='admin-unpair',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_unpair(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        # TODO: Implement unpairing
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @patch(
        path='/admin/pairing/permute/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='admin-permute',
    )
    async def htmx_admin_permute(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template | ClientRedirect:
        # TODO: Implement permute
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @put(
        path='/admin/pairing/set-result-hotkey/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-event-set-result-hotkey',
        data=Body(media_type=RequestEncodingType.URL_ENCODED),
    )
    async def htmx_admin_set_result_hotkey(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        round: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        board_id: int | None = int(data.get('board_id', 0))
        key: str | None = data.get('key')

        if tournament_id is None or not round or board_id is None:
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round,
                board_id=board_id,
            )

        result: int | None = None
        match key:
            case 'Digit1':
                result = Result.GAIN
            case 'Digit2':
                result = Result.LOSS
            case 'Digit3':
                result = Result.DRAW
            case _:
                return HTMXTemplate(
                    template_name='/common/empty.html',
                    re_swap='none',
                    trigger_event='highlight_board',
                    after='receive',
                    params={
                        'board_id': board_id,
                    },
                )

        return self._admin_update_result(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=result,
            trigger_event='highlight_board',
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

    @patch(
        path='/admin/pairing/set-participation/'
        '{event_uniq_id:str}/{tournament_id:int}/{player_id:int}/{round:int}/{action:str}',
        name='admin-set-participation',
    )
    async def htmx_admin_set_participation(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        player_id: int,
        action: str,
    ) -> Template | ClientRedirect:
        web_context = PairingsAdminWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=None,
            player_id=player_id,
        )
        if web_context.error:
            return web_context.error
        assert web_context.admin_tournament is not None
        assert web_context.admin_player is not None

        # If there aren't any pairings, then the round for the bye is the first round
        round_for_participation = web_context.admin_round or 1

        new_byes: dict[int, Result] = {}
        match action:
            case 'ZPB':
                new_byes[round_for_participation] = Result.ZERO_POINT_BYE
            case 'LEAVE':
                new_byes = {
                    r: Result.ZERO_POINT_BYE
                    for r in range(
                        round_for_participation,
                        web_context.admin_tournament.rounds + 1,
                    )
                    if web_context.admin_player.pairings[r].unplayed
                }
            case 'RETURN':
                if round_for_participation < web_context.admin_tournament.current_round:
                    new_byes[round_for_participation] = Result.NO_RESULT
                else:
                    # Return for the rest of the tournament
                    new_byes = {
                        r: Result.NO_RESULT
                        for r in range(
                            round_for_participation,
                            web_context.admin_tournament.rounds + 1,
                        )
                    }
            case 'HPB':
                new_byes[round_for_participation] = Result.HALF_POINT_BYE
            case 'PAIR':
                pass

        if len(new_byes) > 0:
            web_context.admin_tournament.set_player_byes(
                web_context.admin_player, new_byes
            )
            event_loader: EventLoader = EventLoader.get(request=request)
            event_loader.clear_cache(event_uniq_id)

        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @post(
        path='/admin/generate-pairings/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-generate-pairings',
    )
    async def admin_tournament_generate_pairings(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=None,
            board_id=None,
            player_id=None,
            data=None,
        )

        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_tournament is None:
            raise RuntimeError('admin_tournament not defined')

        tournament = web_context.admin_tournament
        assert tournament is not None
        BbpPairings().generate_pairings(tournament)
        tournament.read_papi(True)

        Message.success(
            request,
            _(
                'Pairings of round {round} generated for tournament [{tournament_uniq_id}].'
            ).format(
                round=tournament.current_round, tournament_uniq_id=tournament.uniq_id
            ),
        )
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=None,
            board_id=None,
            trigger_event=None,
        )
