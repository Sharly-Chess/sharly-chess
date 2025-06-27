import json
from dataclasses import dataclass
from typing import Annotated, Any

from litestar import delete, get, patch, put, post
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate
from litestar.channels import ChannelsPlugin

from common.exception import SharlyChessException
from common.i18n import _, ngettext
from common.logger import get_logger
from data.board import Board
from data.player import Player
from data.safety_mode import RoundStatus, SafetyMode, PairingAction
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from utils.enum import Result
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler


logger = get_logger()


@dataclass
class PageIdentifier:
    event_uniq_id: str
    tournament_id: int
    round_: int

    def to_json(self) -> str:
        return json.dumps(
            {
                'event_uniq_id': self.event_uniq_id,
                'tournament_id': self.tournament_id,
                'round_': self.round_,
            }
        )

    @classmethod
    def from_json(cls, json_str) -> 'PageIdentifier':
        data = json.loads(json_str)
        return cls(**data)


class PairingsAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        round_: int | None,
        board_id: int | None = None,
        player_id: int | None = None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None = None,
        action: PairingAction | None = None,
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
            for player in self.admin_tournament.players:
                self.admin_tournament.set_player_points(
                    player, before_round=self.admin_round
                )
            self.admin_boards = self.admin_tournament.build_boards(self.admin_round)
            unpaired = self.admin_tournament.get_unpaired_players(self.admin_boards)

        if SessionHandler.get_session_admin_pairings_show_without_results(request):
            self.admin_filtered_boards = [
                b for b in self.admin_boards if b.result == Result.NO_RESULT
            ]
        else:
            self.admin_filtered_boards = self.admin_boards

        self.admin_unpaired = []
        self.admin_bye_players = []
        if (
            self.admin_tournament
            and self.admin_tournament.pairing_system.split_unpaired_and_bye_players
        ):
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
        else:
            self.admin_unpaired = sorted(unpaired, key=lambda p: p.last_name)

        self.admin_board: Board | None = None
        if board_id is not None:
            self.admin_board = next(
                (b for b in self.admin_boards if b.board_id == board_id), None
            )

        self.admin_player: Player | None = None
        if player_id is not None:
            self.admin_player = next((p for p in unpaired if p.id == player_id), None)

        self.safety_mode = SafetyMode.SAFE
        if tournament_id:
            page_identifier = PageIdentifier(
                event_uniq_id, tournament_id, self.admin_round
            )
            session_page_identifier = (
                SessionHandler.get_session_admin_pairings_page_identifier(request)
            )
            if (
                not session_page_identifier
                or page_identifier != session_page_identifier
            ):
                SessionHandler.set_session_admin_pairings_page_identifier(
                    request, page_identifier
                )
                SessionHandler.set_session_admin_pairings_safety_mode(
                    request, SafetyMode.SAFE
                )
            else:
                self.safety_mode = (
                    SessionHandler.get_session_admin_pairings_safety_mode(request)
                )
        self.requires_refresh = False
        if action:
            permission_handler = (
                self.get_admin_tournament().pairing_system.permission_handler
            )
            try:
                if not permission_handler.validate_action(
                    action, self.round_status, self.safety_mode
                ):
                    SessionHandler.set_session_admin_pairings_safety_mode(
                        request,
                        permission_handler.required_mode(self.round_status, action),
                    )
                    self.requires_refresh = True
            except SharlyChessException:
                self._redirect_error(
                    f'Action [{action}] does not exist for '
                    f'round with status [{self.round_status}].'
                )

    @property
    def template_context(self) -> dict[str, Any]:
        allowed_actions = []
        existing_actions = []
        if self.admin_tournament:
            permission_handler = self.admin_tournament.pairing_system.permission_handler
            allowed_actions = permission_handler.allowed_actions(
                self.round_status, self.safety_mode
            )
            existing_actions = permission_handler.existing_actions(self.round_status)
        return super().template_context | {
            'admin_event_tab': 'admin-event-pairings-tab',
            'admin_tournament': self.admin_tournament,
            'admin_round': self.admin_round,
            'admin_boards': self.admin_boards,
            'round_status': self.round_status,
            'safety_mode': self.safety_mode,
            'allowed_actions': allowed_actions,
            'existing_actions': existing_actions,
        }

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_board(self) -> Board:
        assert self.admin_board is not None
        return self.admin_board

    def get_admin_player(self) -> Player:
        assert self.admin_player is not None
        return self.admin_player


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
        errors: dict[str, str] | None = None,
        trigger_event: str | None = None,
        params: dict[str, Any] | None = None,
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
            case 'pairing-settings':
                assert admin_tournament is not None
                if data is None:
                    data = {}
                    for setting in admin_tournament.pairing_variation.settings:
                        data |= setting.default_form_data(admin_tournament)
                template_context |= {
                    'modal': modal,
                    'pairing_settings': admin_tournament.pairing_variation.settings,
                    'data': data,
                    'errors': errors or {},
                }
        round_ = web_context.admin_round
        template_context |= {
            'admin_tournament_id': web_context.value_to_form_data(admin_tournament.id)
            if admin_tournament
            else None,
            'tournament_options': web_context.get_tournament_options(),
            'admin_filtered_boards': web_context.admin_filtered_boards,
            'admin_unpaired': web_context.admin_unpaired,
            'admin_bye_players': web_context.admin_bye_players,
            'pairings_generation_disabled_message': admin_tournament
            and admin_tournament.pairings_generation_disabled_message(round_),
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

        if web_context.admin_board is not None and modal is None:
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
        show_without_results: bool | None,
    ) -> Template | ClientRedirect:
        if show_without_results is not None:
            SessionHandler.set_session_admin_pairings_show_without_results(
                request, show_without_results
            )
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
            action=None if validate_result else PairingAction.RESULT_UPDATE,
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        board = web_context.get_admin_board()

        if board.exempt:
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round_,
                board_id=board_id,
            )

        target_board_id: int | None
        if result not in (Result.admin_imputable_results()):
            return self.redirect_error(request, f'Invalid result [{result}].')

        if validate_result:
            if board.result != result:
                trigger_event = 'highlight_board_with_warning'
                target_board_id = board_id
            else:
                target_board_id = self._next_board_id(
                    board_id, web_context.admin_filtered_boards
                )
        else:
            tournament.add_result(
                board,
                Result.from_papi_value(result),
                web_context.admin_round,
            )
            target_board_id = self._next_board_id(
                board_id, web_context.admin_filtered_boards
            )

        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
            board_id=None if web_context.requires_refresh else board_id,
            trigger_event=trigger_event,
            params={'board_id': target_board_id},
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
        name='admin-pairings-set-result',
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
        name='admin-pairings-unpair-board',
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
            action=PairingAction.MANUAL_UNPAIRING,
        )
        if web_context.error:
            return web_context.error
        board = web_context.get_admin_board()
        tournament = web_context.get_admin_tournament()
        tournament.unpair_boards([board], round)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @patch(
        path='/admin/pairing/permute/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='admin-pairings-permute',
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
            action=PairingAction.COLOR_PERMUTE,
        )
        if web_context.error:
            return web_context.error
        board = web_context.get_admin_board()
        tournament = web_context.get_admin_tournament()
        tournament.permute_board_colors(board, round)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @put(
        path='/admin/pairing/set-result-hotkey/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-set-result-hotkey',
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
                )

        return self._admin_update_result(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=result,
            validate_result=data['validate_result'] == 'true',
        )

    @patch(
        path=(
            '/admin/pairing/set-participation/{event_uniq_id:str}/'
            '{tournament_id:int}/{player_id:int}/{round:int}/{action:str}'
        ),
        name='admin-pairings-set-participation',
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
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            player_id=player_id,
            action=(
                PairingAction.MANUAL_PAIRING
                if action == 'PAIR'
                else PairingAction.BYE_UPDATE
            ),
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        player = web_context.get_admin_player()

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
                        tournament.rounds + 1,
                    )
                    if player.pairings[r].unplayed
                }
            case 'RETURN':
                if round_for_participation < tournament.current_round:
                    new_byes[round_for_participation] = Result.NO_RESULT
                else:
                    # Return for the rest of the tournament
                    new_byes = {
                        r: Result.NO_RESULT
                        for r in range(
                            round_for_participation,
                            tournament.rounds + 1,
                        )
                    }
            case 'HPB':
                byes: int = 0
                for pairing in player.pairings.values():
                    match pairing.result:
                        case Result.HALF_POINT_BYE:
                            byes += 1
                        case Result.FULL_POINT_BYE:
                            byes += 2
                if byes >= tournament.max_byes:
                    Message.error(
                        request,
                        _('Too many byes for player [{player_name}].').format(
                            player_name=player.last_name
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
                    tournament.create_round_pairing(
                        round_for_participation,
                        exempt_player.id,
                        player.id,
                    )
                else:
                    tournament.create_round_pairing(
                        round_for_participation,
                        player.id,
                        None,
                    )

        tournament.set_player_byes(player, new_byes)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @post(
        path='/admin/pairings/generate/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-generate-round-pairings',
    )
    async def admin_generate_round_pairings(
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
            action=PairingAction.FULL_PAIRING,
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        round_ = web_context.admin_round
        if not tournament.are_pairing_settings_valid:
            tournament.set_default_pairing_settings()
        tournament.pairing_variation.engine.generate_pairings(tournament, round_)
        Message.success(request, _('Pairings successfully generated!'))
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
        )

    @post(
        path='/admin/pairings/generate-partial/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-generate-round-partial-pairings',
    )
    async def admin_generate_round_partial_pairings(
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
            action=PairingAction.PARTIAL_PAIRING,
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        round_ = web_context.admin_round
        if not tournament.are_pairing_settings_valid:
            tournament.set_default_pairing_settings()
        tournament.pairing_variation.engine.generate_pairings(tournament, round_, True)
        unpaired_count = sum(
            player.pairings[round_].not_paired for player in tournament.players
        )
        if unpaired_count:
            if unpaired_count == 1:
                reason = (
                    _('PAB is already assigned')
                    if tournament.round_has_pab(round_)
                    else _('player already received a PAB in a previous round')
                )
            else:
                reason = _('some already played each other')
            Message.warning(
                request,
                ' '.join(
                    [
                        _('Complementary pairings generated.'),
                        ngettext(
                            '{players} player remain unpaired',
                            '{players} players remain unpaired',
                            unpaired_count,
                        ).format(players=unpaired_count),
                        f'({reason}).',
                    ]
                ),
            )
        else:
            Message.success(
                request,
                _('Complementary pairings successfully generated!'),
            )
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round_,
        )

    @post(
        path='/admin/pairings/generate/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-generate-tournament-pairings',
    )
    async def admin_generate_tournament_pairings(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
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
            data=data,
        )
        tournament = web_context.get_admin_tournament()
        if errors := self._validate_pairing_settings(tournament, data):
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=None,
                data=data,
                errors=errors,
                modal='pairing-settings',
            )
        self._save_pairing_settings_data(tournament, data)
        for round_ in range(1, tournament.rounds + 1):
            tournament.pairing_variation.engine.generate_pairings(tournament, round_)
        tournament.set_current_round(1)
        Message.success(
            request,
            _(
                'Pairings generated for all rounds of '
                'tournament [{tournament_uniq_id}].'
            ).format(tournament_uniq_id=tournament.uniq_id),
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
        name='admin-pairings-unpair-round',
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
            action=PairingAction.FULL_UNPAIRING,
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        tournament.unpair_boards(web_context.admin_boards, round)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @post(
        path='/admin/pairings/unpair-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-pairings-unpair-tournament',
    )
    async def admin_pairings_unpair_tournament(
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
        )
        if web_context.error:
            return web_context.error
        tournament = web_context.get_admin_tournament()
        for round_ in reversed(range(1, tournament.rounds + 1)):
            boards = tournament.build_boards(round_)
            tournament.unpair_boards(boards, round_)
        tournament.set_current_round(0)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=1,
        )

    @get(
        path=(
            '/admin/pairings/safety-mode-modal/{event_uniq_id:str}/{tournament_id:int}'
            '/{round:int}/{action:str}/{redirect_method:str}/{redirect_route:path}'
        ),
        name='admin-pairings-safety-mode-modal',
    )
    async def admin_pairings_safety_mode_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        action: str,
        redirect_method: str,
        redirect_route: str,
    ) -> Template | ClientRedirect:
        try:
            protected_action = PairingAction(action)
        except ValueError:
            return self.redirect_error(request, f'Unknown pairing action [{action}]')
        web_context = PairingsAdminWebContext(
            request, event_uniq_id, tournament_id, round
        )
        if web_context.error:
            return web_context.error

        tournament = web_context.get_admin_tournament()
        template_context = web_context.template_context
        template_context |= {
            'modal': 'safety-mode',
            'action': protected_action,
            'required_mode': (
                tournament.pairing_system.permission_handler.required_mode(
                    web_context.round_status, protected_action
                )
            ),
            'redirect_method': redirect_method,
            'redirect_route': redirect_route,
        }
        return self._admin_event_render(template_context)

    @post(
        path=[
            '/admin/pairings/update-safety-mode/'
            '{event_uniq_id:str}/{tournament_id:int}/{round:int}',
            '/admin/pairings/update-safety-mode/{event_uniq_id:str}'
            '/{tournament_id:int}/{round:int}/{mode:str}',
        ],
        name='admin-pairings-update-safety-mode',
    )
    async def admin_pairings_update_safety_mode(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ) -> Template | ClientRedirect:
        mode = WebContext.form_data_to_str(data, 'mode') or ''
        try:
            SessionHandler.set_session_admin_pairings_safety_mode(
                request, SafetyMode(mode)
            )
        except ValueError:
            return self.redirect_error(request, f'Unknown safety mode [{mode}]')
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
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
        )
        if web_context.error:
            return web_context.error
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
        )

        if web_context.error:
            return web_context.error

        player = web_context.get_admin_player()
        tournament = web_context.get_admin_tournament()
        tournament.check_in_player(player, bool(check_in))
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @get(
        path='/admin/pairings/settings-modal/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-settings-modal',
    )
    async def admin_pairings_settings_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request, event_uniq_id, tournament_id, round
        )
        tournament = web_context.get_admin_tournament()
        data: dict[str, str] = {}
        for setting in tournament.pairing_variation.settings:
            data |= setting.get_form_data(tournament)
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            modal='pairing-settings',
            data=data,
        )

    @post(
        path='/admin/pairings/generate-with-settings/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-generate-round-pairings-with-settings',
    )
    async def htmx_admin_generate_round_pairings_with_settings(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
            data=data,
        )
        tournament = web_context.get_admin_tournament()
        if errors := self._validate_pairing_settings(tournament, data):
            return self._admin_event_pairings_render(
                request,
                event_uniq_id=event_uniq_id,
                tournament_id=tournament_id,
                round_=round,
                data=data,
                errors=errors,
                modal='pairing-settings',
            )
        self._save_pairing_settings_data(tournament, data)
        tournament.pairing_variation.engine.generate_pairings(
            tournament, web_context.admin_round
        )
        Message.success(request, _('Pairings successfully generated!'))
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=round,
        )

    @staticmethod
    def _validate_pairing_settings(
        tournament: Tournament, data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        for setting in tournament.pairing_variation.settings:
            errors |= setting.get_data_errors(tournament, data)
        return errors

    @staticmethod
    def _save_pairing_settings_data(tournament: Tournament, data: dict[str, str]):
        stored_settings: dict[str, Any] = {}
        for setting in tournament.pairing_variation.settings:
            stored_settings[setting.id] = setting.to_stored_value(
                setting.from_form_data(data)
            )
        tournament.update_pairing_settings(stored_settings)

    @put(
        path='/admin/tournament/set-current-round/{event_uniq_id:str}/{tournament_id:int}/{current_round:int}',
        name='admin-tournament-set-current-round',
    )
    async def htmx_admin_tournament_set_current_round(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        current_round: int,
    ) -> Template | ClientRedirect:
        with EventDatabase(event_uniq_id, True) as database:
            database.set_tournament_current_round(tournament_id, current_round)
            database.commit()
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round_=current_round,
        )

    @get(
        path='/admin/pairings/needs-refresh-message/{event_uniq_id:str}/{tournament_id:int}/{round:int}/{reason:str}',
        name='admin-pairings-needs-refresh-message',
    )
    async def htmx_admin_pairings_refresh_message(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        reason: str,
    ) -> Template:
        return HTMXTemplate(
            template_name='/admin/common/needs_refresh.html',
            context={
                'url': request.app.route_reverse(
                    'admin-event-pairings-tab',
                    event_uniq_id=event_uniq_id,
                    tournament_id=tournament_id,
                    round=round,
                ),
                'reason': reason,
            },
        )

    @classmethod
    def publish_new_user_results(
        cls,
        channels: ChannelsPlugin,
        event_uniq_id: str,
        tournament_id: int,
        round_: int,
    ):
        channels.publish(
            {
                'event': f'new-user-results/{event_uniq_id}/{tournament_id}/{round_}',
                'data': '',
            },
            ['sse'],
        )
        channels.publish(
            {
                'event': f'new-user-results/{event_uniq_id}',
                'data': '',
            },
            ['sse'],
        )
