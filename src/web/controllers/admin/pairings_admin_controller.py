from dataclasses import dataclass
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
from common.logger import get_logger
from data.loader import EventLoader
from data.board import Board
from data.event import Event
from data.player import Player
from data.permission import RoundStatus, SafetyMode, PermissionHandler, Action
from data.tournament import Tournament
from pairing.bbp_pairings import BbpPairings
from utils.enum import Result
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import BaseController
from web.messages import Message
from web.session import SessionHandler


logger = get_logger()


@dataclass
class PageIdentifier:
    event_uniq_id: str
    tournament_id: int
    round_: int


class PairingsAdminWebContext(BaseEventAdminWebContext):
    page_identifier: PageIdentifier | None = None
    safety_mode: SafetyMode = SafetyMode.SAFE

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
            else self.admin_tournament.current_round or 1
            if self.admin_tournament is not None
            else 0
        )

        self.round_status = RoundStatus.from_round(
            self.admin_round,
            self.admin_tournament.current_round if self.admin_tournament else 0,
        )

        self.admin_boards: list[Board] = []
        unpaired: list[Player] = []
        if self.admin_tournament is not None:
            self.admin_tournament.calculate_points_before_round(
                before_round=self.admin_round
            )
            self.admin_boards, unpaired = self.admin_tournament.build_boards(
                self.admin_round
            )

        if SessionHandler.get_session_admin_pairings_show_without_results(request):
            self.admin_filtered_boards = [
                b for b in self.admin_boards if b.result == Result.NO_RESULT
            ]
        else:
            self.admin_filtered_boards = self.admin_boards

        self.admin_unpaired = []
        self.admin_bye_players = []
        for player in sorted(unpaired, key=lambda p: p.last_name):
            if player.pairings[self.admin_round] and player.pairings[
                self.admin_round
            ].result in (
                Result.ZERO_POINT_BYE,
                Result.HALF_POINT_BYE,
                Result.FULL_POINT_BYE,
            ):
                self.admin_bye_players.append(player)
            else:
                self.admin_unpaired.append(player)

        self.admin_board: Board | None = None
        if board_id is not None and self.admin_boards is not None:
            self.admin_board = next(
                (b for b in self.admin_boards if b.board_id == board_id), None
            )

        self.admin_player: Player | None = None
        if player_id is not None:
            self.admin_player = next((p for p in unpaired if p.id == player_id), None)

        cls = self.__class__
        if not tournament_id:
            cls.page_identifier = None
            cls.safety_mode = SafetyMode.SAFE
        else:
            page_identifier = PageIdentifier(
                event_uniq_id, tournament_id, self.admin_round
            )
            if not cls.page_identifier or cls.page_identifier != page_identifier:
                cls.page_identifier = page_identifier
                cls.safety_mode = SafetyMode.SAFE

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tournament': self.admin_tournament,
            'round_status': self.round_status,
            'safety_mode': self.safety_mode,
            'allowed_actions': PermissionHandler.allowed_actions(
                self.round_status, self.safety_mode
            ),
            'existing_actions': PermissionHandler.existing_actions(self.round_status),
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
        params: dict[str, Any] | None = None,
        full_refresh: bool = False,
        admin_pairings_show_without_results: bool | None = None,
        protected_action: Action | None = None,
    ) -> Template | ClientRedirect:
        if admin_pairings_show_without_results is not None:
            SessionHandler.set_session_admin_pairings_show_without_results(
                request, admin_pairings_show_without_results
            )

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

        template_context |= {
            'admin_pairings_show_without_results': SessionHandler.get_session_admin_pairings_show_without_results(
                request
            ),
        }

        match modal:
            case None:
                pass
            case 'unpaired-player':
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
            case 'safety-mode':
                round_status = web_context.round_status
                required_mode = PermissionHandler.required_mode(
                    round_status, protected_action
                )
                enabled_actions: list[Action] = []
                safety_mode = web_context.safety_mode
                assert safety_mode is not None
                if safety_mode == SafetyMode.SAFE:
                    enabled_actions += PermissionHandler.unsafe_actions(round_status)
                if required_mode == SafetyMode.FIDE_INCOMPATIBLE:
                    enabled_actions += PermissionHandler.fide_incompatible_actions(
                        round_status
                    )
                template_context |= {
                    'modal': modal,
                    'action': protected_action,
                    'enabled_actions': enabled_actions,
                    'required_mode': required_mode,
                }
            case 'unfinished-round':
                template_context |= {
                    'modal': modal,
                    'admin_unpaired_player_count': len(web_context.admin_unpaired),
                    'admin_no_result_board_count': len(
                        [
                            board
                            for board in web_context.admin_boards
                            if board.result == Result.NO_RESULT
                        ]
                    ),
                }
        round_ = web_context.admin_round
        template_context |= {
            'admin_event_tab': 'admin-event-pairings-tab',
            'admin_event': admin_event,
            'admin_tournament': admin_tournament,
            'admin_tournament_id': web_context.value_to_form_data(admin_tournament.id)
            if admin_tournament
            else None,
            'tournament_options': web_context.get_tournament_options(),
            'admin_round': round_,
            'admin_boards': web_context.admin_boards,
            'admin_filtered_boards': web_context.admin_filtered_boards,
            'admin_unpaired': web_context.admin_unpaired,
            'admin_bye_players': web_context.admin_bye_players,
            'pairings_generation_allowed': admin_tournament
            and (admin_tournament.pairings_generation_allowed(round_)),
            'board': web_context.admin_board,
            'extra_row_class': 'highlight highlight-warning'
            if trigger_event == 'highlight_board_with_warning'
            else '',
            'wp': web_context.admin_board.white_player
            if web_context.admin_board
            else None,
            'bp': web_context.admin_board.black_player
            if web_context.admin_board
            else None,
        }

        if not full_refresh and web_context.admin_board is not None and modal is None:
            return HTMXTemplate(
                template_name='/admin/pairings/pairing_row_and_controls.html',
                context=template_context,
                re_target='#round-controls',
                re_swap='outerHTML',
                trigger_event=trigger_event,
                after='receive',
                params=params,
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
        admin_pairings_show_without_results: bool | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            admin_pairings_show_without_results=admin_pairings_show_without_results,
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
        result: int,
        trigger_event: str | None = None,
        validate_result: bool = False,
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
        event = web_context.admin_event
        tournament = web_context.admin_tournament
        board = web_context.admin_board
        if event is None:
            raise RuntimeError('admin_event not defined')
        if tournament is None:
            raise RuntimeError('admin_tournament not defined')
        if board is None:
            raise RuntimeError('admin_board not defined')

        if board.exempt:
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round_,
            )

        target_board_id: int | None
        was_round_finished = tournament.is_round_finished(round_)
        if result not in (Result.admin_imputable_results()):
            return BaseController.redirect_error(request, f'Invalid result [{result}].')

        if validate_result:
            if board.result != result:
                trigger_event = 'highlight_board_with_warning'
                target_board_id = board_id
            else:
                target_board_id = self._next_board_id(
                    board_id, web_context.admin_filtered_boards
                )
        else:
            if not PermissionHandler.validate_action(
                Action.RESULT_UPDATE,
                web_context.round_status,
                web_context.safety_mode,
            ):
                return self._admin_event_pairings_render(
                    request,
                    event_uniq_id=event_uniq_id,
                    tournament_id=tournament_id,
                    round_=round_,
                    modal='safety-mode',
                    protected_action=Action.RESULT_UPDATE,
                )
            tournament.add_result(
                board,
                Result.from_papi_value(result),
                web_context.admin_round,
            )
            EventLoader.get(request=request).reload_tournament(
                event.uniq_id, tournament.id
            )
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
            target_board_id = self._next_board_id(
                board_id, web_context.admin_filtered_boards
            )

        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            trigger_event=trigger_event,
            params={'board_id': target_board_id},
            full_refresh=tournament.is_round_finished(round_) != was_round_finished,
        )

    @staticmethod
    def _next_board_id(board_id: int, boards: list[Board]) -> int | None:
        return next(
            (
                b.board_id
                for b in boards
                if b.board_id is not None and b.board_id > board_id
            ),
            None,
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
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            player_id=None,
            data=None,
        )
        if not PermissionHandler.validate_action(
            Action.MANUAL_UNPAIRING,
            web_context.round_status,
            web_context.safety_mode,
        ):
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round,
                modal='safety-mode',
                protected_action=Action.MANUAL_UNPAIRING,
            )
        board = web_context.admin_board
        tournament = web_context.admin_tournament
        assert board is not None
        assert tournament is not None
        tournament.unpair_boards([board], round)
        EventLoader.get(request=request).reload_tournament(event_uniq_id, tournament.id)
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
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            player_id=None,
            data=None,
        )
        if not PermissionHandler.validate_action(
            Action.COLOR_PERMUTE,
            web_context.round_status,
            web_context.safety_mode,
        ):
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round,
                modal='safety-mode',
                protected_action=Action.COLOR_PERMUTE,
            )
        board = web_context.admin_board
        tournament = web_context.admin_tournament
        assert board is not None
        assert tournament is not None
        tournament.permute_board_colors(board, round)
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
        tournament_id: int,
        round: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        board_id: int = int(data['board_id'])
        key: str = data['key']

        result: int | None = None
        match key:
            case 'Digit0' | 'Numpad0':
                result = Result.NO_RESULT
            case 'Digit1' | 'Numpad1':
                result = Result.GAIN
            case 'Digit2' | 'Numpad2':
                result = Result.LOSS
            case 'Digit3' | 'Numpad3':
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
            validate_result=data['validate_result'] == 'true',
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
            trigger_event='close_modal',
            result=Result.NO_RESULT.value,
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
        protected_action = (
            Action.MANUAL_PAIRING if action == 'PAIR' else Action.BYE_UPDATE
        )
        if not PermissionHandler.validate_action(
            protected_action,
            web_context.round_status,
            web_context.safety_mode,
        ):
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round,
                modal='safety-mode',
                protected_action=protected_action,
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
                byes: int = 0
                for pairing in web_context.admin_player.pairings.values():
                    match pairing.result:
                        case Result.HALF_POINT_BYE:
                            byes += 1
                        case Result.FULL_POINT_BYE:
                            byes += 2
                if byes >= web_context.admin_tournament.max_byes:
                    Message.error(
                        request,
                        _('Too many byes for player [{player_name}].').format(
                            player_name=web_context.admin_player.last_name
                        ),
                    )
                else:
                    new_byes[round_for_participation] = Result.HALF_POINT_BYE
            case 'PAIR':
                exempt_player = next(
                    (b.white_player for b in web_context.admin_boards if b.exempt),
                    None,
                )
                if exempt_player is not None:
                    web_context.admin_tournament.create_round_pairing(
                        round_for_participation,
                        exempt_player.id,
                        web_context.admin_player.id,
                    )
                else:
                    web_context.admin_tournament.create_round_pairing(
                        round_for_participation,
                        web_context.admin_player.id,
                        None,
                    )

        web_context.admin_tournament.set_player_byes(web_context.admin_player, new_byes)
        EventLoader.get(request=request).reload_tournament(event_uniq_id, tournament_id)

        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @post(
        path='/admin/generate-pairings/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-tournament-generate-pairings',
    )
    async def admin_tournament_generate_pairings(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=None,
            player_id=None,
            data=None,
        )
        if not PermissionHandler.validate_action(
            Action.FULL_PAIRING,
            web_context.round_status,
            web_context.safety_mode,
        ):
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round,
                modal='safety-mode',
                protected_action=Action.FULL_PAIRING,
            )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_tournament is None:
            raise RuntimeError('admin_tournament not defined')

        tournament = web_context.admin_tournament
        assert tournament is not None
        BbpPairings().generate_pairings(tournament, web_context.admin_round)
        EventLoader.get(request=request).reload_tournament(event_uniq_id, tournament_id)
        Message.success(
            request,
            _(
                'Pairings of round {round} generated for tournament [{tournament_uniq_id}].'
            ).format(
                round=web_context.admin_round, tournament_uniq_id=tournament.uniq_id
            ),
        )
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=web_context.admin_round,
            board_id=None,
            trigger_event=None,
        )

    @post(
        path='/admin/pairings/unpair/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-unpair',
    )
    async def admin_pairings_unpair(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=None,
            player_id=None,
            data=None,
        )
        PermissionHandler.validate_action(
            Action.FULL_UNPAIRING,
            web_context.round_status,
            web_context.safety_mode,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        tournament = web_context.admin_tournament
        if tournament is None:
            raise RuntimeError('admin_tournament not defined')
        boards = web_context.admin_boards
        assert boards is not None
        tournament.unpair_boards(boards, round)
        EventLoader.get(request=request).reload_tournament(event_uniq_id, tournament_id)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @post(
        path='/admin/pairings/update-safety-mode/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{mode:str}',
        name='admin-pairings-update-safety-mode',
    )
    async def admin_pairings_update_safety_mode(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        mode: str,
    ) -> Template | ClientRedirect:
        try:
            PairingsAdminWebContext.safety_mode = SafetyMode(mode)
        except ValueError:
            logger.error(f'Unknown safety mode [{mode}]')
            Message.error(request, _('An error occurred.'))
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            full_refresh=True,
        )

    @get(
        path='/admin/pairings/safety-mode-modal/{event_uniq_id:str}/{tournament_id:int}/{round:int}/{action:str}',
        name='admin-pairings-safety-mode-modal',
    )
    async def admin_pairings_safety_mode_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        action: str,
    ) -> Template | ClientRedirect:
        modal: str | None = 'safety-mode'
        protected_action: Action | None = None
        try:
            protected_action = Action(action)
        except ValueError:
            logger.error(f'Unknown pairing action [{action}]')
            Message.error(request, _('An error occurred.'))
            modal = None
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            modal=modal,
            protected_action=protected_action,
        )

    @get(
        path='/admin/pairings/unfinished-round-modal/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-unfinished-round-modal',
    )
    async def admin_pairings_unfinished_round_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
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

        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            modal='unfinished-round',
        )

    @post(
        path='/admin/pairings-check-in-out/{event_uniq_id:str}/{tournament_id:int}/{round:int}/{player_id:int}/{check_in:int}',
        name='admin-pairings-check-in-out',
    )
    async def htmx_admin_pairings_check_in_out(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        player_id: int,
        check_in: int,
        round: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            player_id=player_id,
            round_=round,
            board_id=None,
            data=None,
        )

        if web_context.error:
            return web_context.error
        if web_context.admin_player is None:
            raise RuntimeError('admin_player not defined')
        admin_player: Player = web_context.admin_player
        assert admin_player.tournament is not None
        admin_player.tournament.check_in_player(admin_player, bool(check_in))
        EventLoader.get(request=request).reload_tournament(event_uniq_id, tournament_id)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )
