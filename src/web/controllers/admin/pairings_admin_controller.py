from operator import attrgetter

from litestar.exceptions import NotFoundException, ClientException

from common import experimental_features_enabled

from collections import defaultdict
from typing import Annotated, Any, Optional

from data.access_levels.actions import AuthAction
from data.input_output import DataSourceManager
from data.pairings.engines import BbpPairings
from data.pairings.bbp_history import TournamentHistoryPlayer
from litestar import delete, get, patch, put, post
from litestar.plugins.htmx import HTMXRequest
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
from data.player import TournamentPlayer
from data.event import Event
from data.team import Team
from data.team_board import TeamBoard
from data.print_documents.documents import (
    PairingPrintDocument,
    PlayerRankingPrintDocument,
)
from data.safety_mode import RoundStatus, SafetyMode, PairingAction
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from utils.enum import Result, CheckInStatus
from plugins.manager import plugin_manager
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.base_controller import WebContext
from web.guards import (
    EventGuard,
    TournamentActionGuard,
    SetResultGuard,
)
from web.messages import Message
from web.session import (
    SessionPairingsShowWithoutResults,
    SessionPairingsSafetyMode,
    PairingsPageIdentifier,
    SessionPairingsPageIdentifier,
    SessionPairingsSelectedTournament,
    SessionPairingsSelectedRound,
)

logger = get_logger()


class PairingsAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        round_: int | None = None,
        board_id: int | None = None,
        player_id: int | None = None,
        action: PairingAction | None = None,
        load_check_in_data: bool = False,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        self.admin_tournament: Tournament | None = None
        self.allowed_tournaments = self.client.allowed_tournaments_for_action(
            AuthAction.VIEW_PAIRINGS_TAB
        )
        event = self.get_admin_event()
        if tournament_id:
            if tournament_id not in event.tournaments_by_id:
                raise NotFoundException(
                    f'Unknown tournament ID [{tournament_id}] '
                    f'for event [{event.uniq_id}]'
                )
            self.admin_tournament = event.tournaments_by_id[tournament_id]
        elif self.allowed_tournaments:
            session_tournament_id = SessionPairingsSelectedTournament(
                self.request, event
            ).get()
            if session_tournament_id in [
                tournament.id for tournament in self.allowed_tournaments
            ]:
                self.admin_tournament = event.tournaments_by_id[session_tournament_id]
            else:
                self.admin_tournament = self.allowed_tournaments[0]
        if load_check_in_data:
            plugin_manager.hook_for_event(event, 'load_tournament_check_in_data')(
                tournament=self.get_admin_tournament()
            )

        self.display_rankings = self.admin_tournament and (
            self.admin_tournament.finished
            and (round_ is None or round_ > self.admin_tournament.rounds)
        )

        if self.admin_tournament is None:
            self.admin_round = 0
        elif round_:
            self.admin_round = round_
        elif session_round := SessionPairingsSelectedRound(
            self.request, self.admin_tournament
        ).get():
            max_round = (
                self.admin_tournament.current_round or 1
            ) + self.admin_tournament.finished
            self.admin_round = min(session_round, max_round)
        else:
            self.admin_round = self.admin_tournament.current_round or 1

        if self.admin_tournament and (
            self.admin_round > self.admin_tournament.rounds or self.display_rankings
        ):
            self.admin_round = self.admin_tournament.rounds

        self.round_status = RoundStatus.from_round(
            self.admin_round,
            self.admin_tournament.current_round if self.admin_tournament else 0,
        )

        self.admin_boards: list[Board] = []
        if self.admin_tournament is not None:
            self.admin_tournament.set_for_round(self.admin_round)
            self.admin_boards = self.admin_tournament.get_round_boards(self.admin_round)

        if self.admin_tournament and self.display_rankings:
            self.admin_tournament.compute_tournament_player_ranks()

        if SessionPairingsShowWithoutResults(request).get():
            self.admin_filtered_boards = [
                b for b in self.admin_boards if b.result == Result.NO_RESULT
            ]
        else:
            self.admin_filtered_boards = self.admin_boards

        self.admin_unpaired: list[TournamentPlayer] = []
        self.admin_bye_players: list[TournamentPlayer] = []
        self.admin_absent_players: list[TournamentPlayer] = []
        self.admin_team_bye: list[Team] = []
        self.admin_team_unpaired: list[Team] = []
        self.reload_unpaired_player_lists()
        self.reload_unpaired_team_lists()

        self.admin_board: Board | None = None
        if board_id is not None:
            self.admin_board = next(
                (b for b in self.admin_boards if b.identifier == board_id), None
            )
            if self.admin_board is None and not event.is_team_event:
                self.admin_board = next(
                    (b for b in self.admin_boards if b.board_id == board_id), None
                )

        self.admin_player: TournamentPlayer | None = None
        if player_id is not None:
            assert self.admin_tournament is not None
            self.admin_player = next(
                (
                    p
                    for p in self.admin_tournament.tournament_players
                    if p.id == player_id
                ),
                None,
            )

        self.safety_mode = SafetyMode.SAFE
        if not tournament_id:
            # Reset the session safety mode if coming from another page
            SessionPairingsPageIdentifier(request).unset()
        else:
            page_identifier = PairingsPageIdentifier(
                event.uniq_id, tournament_id, self.admin_round
            )

            session_page_identifier = SessionPairingsPageIdentifier(request).get()
            if page_identifier != session_page_identifier:
                SessionPairingsPageIdentifier(request).set(page_identifier)
                SessionPairingsSafetyMode(request).set(SafetyMode.SAFE)
            else:
                self.safety_mode = SessionPairingsSafetyMode(request).get()
        self.requires_refresh = False
        if action:
            permission_handler = (
                self.get_admin_tournament().pairing_system.permission_handler
            )
            try:
                if not permission_handler.validate_action(
                    action, self.round_status, self.safety_mode
                ):
                    required_mode = permission_handler.required_mode(
                        self.round_status, action
                    )
                    SessionPairingsSafetyMode(request).set(required_mode)
                    self.safety_mode = required_mode
                    self.requires_refresh = True
            except SharlyChessException:
                raise ClientException(
                    f'Action [{action}] does not exist for '
                    f'round with status [{self.round_status}].'
                )

    def reload_unpaired_player_lists(self):
        self.admin_absent_players = []
        self.admin_bye_players = []
        self.admin_unpaired = []
        if not self.admin_tournament:
            return
        # Team-vs-team systems pair teams, not individual players; the unpaired
        # / bye / absent player sidebar isn't meaningful in that mode.
        if (
            self.admin_tournament.event.is_team_event
            and self.admin_tournament.pairing_system.paired_by_team
        ):
            return
        unpaired = self.admin_tournament.get_unpaired_tournament_players(
            self.admin_boards
        )
        if self.admin_tournament.pairing_system.split_unpaired_and_bye_players:
            for player in sorted(unpaired, key=attrgetter('name_sort_key')):
                check_in_status = player.check_in_status_for_round(self.admin_round)
                if check_in_status == CheckInStatus.ABSENT:
                    self.admin_absent_players.append(player)
                elif check_in_status == CheckInStatus.PRESENT:
                    self.admin_unpaired.append(player)
                else:
                    self.admin_bye_players.append(player)
        else:
            self.admin_unpaired = sorted(unpaired, key=attrgetter('name_sort_key'))

    def reload_unpaired_team_lists(self):
        """Populate the team-side equivalents of the player byes /
        unpaired lists.

        Manual byes (HPB / FPB / ZPB) sit in ``admin_team_bye`` and
        are rendered in the side column only — they're hidden from
        the main team-blocks table. Teams without any envelope for
        the round are *to-pair* and land in ``admin_team_unpaired``.
        PAB envelopes are engine-assigned and stay on the main table
        as bye blocks; they don't appear in either list."""
        self.admin_team_bye = []
        self.admin_team_unpaired = []
        if not self.admin_tournament:
            return
        if not (
            self.admin_tournament.event.is_team_event
            and self.admin_tournament.pairing_system.paired_by_team
        ):
            return
        teams = [
            team
            for team in self.admin_tournament.event.sorted_teams
            if team.tournament_id == self.admin_tournament.id
        ]
        on_board_team_ids: set[int] = set()
        manual_bye_team_ids: set[int] = set()
        for team_board in self.admin_tournament.get_round_team_boards(self.admin_round):
            stb = team_board.stored_team_board
            if stb.team_b_id is None and stb.bye_type in (
                'HPB',
                'FPB',
                'ZPB',
            ):
                manual_bye_team_ids.add(stb.team_a_id)
                continue
            on_board_team_ids.add(stb.team_a_id)
            if stb.team_b_id is not None:
                on_board_team_ids.add(stb.team_b_id)
        teams_by_id = {team.id: team for team in teams}
        for team_id in manual_bye_team_ids:
            team = teams_by_id.get(team_id)
            if team is not None:
                self.admin_team_bye.append(team)
        for team in teams:
            if team.id not in on_board_team_ids and team.id not in manual_bye_team_ids:
                self.admin_team_unpaired.append(team)

    @property
    def template_context(self) -> dict[str, Any]:
        allowed_actions = []
        existing_actions = []

        default_print_document = PairingPrintDocument.static_id()

        if self.admin_tournament:
            permission_handler = self.admin_tournament.pairing_system.permission_handler
            allowed_actions = permission_handler.allowed_actions(
                self.round_status, self.safety_mode
            )
            existing_actions = permission_handler.existing_actions(self.round_status)

            if (
                self.display_rankings
                or self.admin_round < self.admin_tournament.current_round
                or self.admin_tournament.is_round_finished(self.admin_round)
            ):
                default_print_document = PlayerRankingPrintDocument.static_id()

        tournament_ids = [tournament.id for tournament in self.allowed_tournaments]
        current_index = (
            tournament_ids.index(self.admin_tournament.id)
            if self.admin_tournament
            else 0
        )
        prev_tournament_id = (
            tournament_ids[current_index - 1] if current_index > 0 else None
        )
        next_tournament_id = (
            tournament_ids[current_index + 1]
            if current_index < len(tournament_ids) - 1
            else None
        )

        return super().template_context | {
            'admin_event_tab': 'admin-event-pairings-tab',
            'admin_tournament': self.admin_tournament,
            'admin_tournament_id': self.value_to_form_data(self.admin_tournament.id)
            if self.admin_tournament
            else None,
            'prev_tournament_id': prev_tournament_id,
            'next_tournament_id': next_tournament_id,
            'admin_round': self.admin_round,
            'admin_boards': self.admin_boards,
            'round_status': self.round_status,
            'display_rankings': self.display_rankings,
            'safety_mode': self.safety_mode,
            'allowed_actions': allowed_actions,
            'existing_actions': existing_actions,
            'tournament_options': self.get_tournament_options(self.allowed_tournaments),
            'admin_filtered_boards': self.admin_filtered_boards,
            'admin_team_boards': (
                [
                    tb
                    for tb in self.admin_tournament.get_round_team_boards(
                        self.admin_round
                    )
                    if not (
                        tb.stored_team_board.team_b_id is None
                        and tb.stored_team_board.bye_type in ('HPB', 'FPB', 'ZPB')
                    )
                ]
                if self.admin_tournament
                else []
            ),
            'admin_unpaired': self.admin_unpaired,
            'admin_bye_players': self.admin_bye_players,
            'admin_absent_players': self.admin_absent_players,
            'admin_team_bye': self.admin_team_bye,
            'admin_team_unpaired': self.admin_team_unpaired,
            'pairings_generation_disabled_message': self.admin_tournament
            and self.admin_tournament.pairings_generation_disabled_message(
                self.admin_round
            ),
            'show_without_results': SessionPairingsShowWithoutResults(
                self.request
            ).get(),
            'board': self.admin_board,
            'wtp': self.admin_board.optional_white_tournament_player
            if self.admin_board
            else None,
            'btp': self.admin_board.black_tournament_player
            if self.admin_board
            else None,
            'experimental_features_enabled': experimental_features_enabled(),
            'default_print_document': default_print_document,
        }

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_board(self) -> Board:
        assert self.admin_board is not None
        return self.admin_board

    def get_admin_player(self) -> TournamentPlayer:
        assert self.admin_player is not None
        return self.admin_player


class PairingsAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        TournamentActionGuard(AuthAction.VIEW_PAIRINGS_TAB),
    ]

    @classmethod
    def _admin_event_pairings_render(
        cls,
        web_context: PairingsAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {}),
        )

    @get(
        path=[
            '/event/{event_uniq_id:str}/pairings',
            '/event/{event_uniq_id:str}/pairings/{tournament_id:int}',
            '/event/{event_uniq_id:str}/pairings/{tournament_id:int}/{round:int}',
        ],
        name='admin-event-pairings-tab',
    )
    async def htmx_admin_pairings_tab(
        self,
        request: HTMXRequest,
        tournament_id: int | None,
        round: int | None,
        show_without_results: bool | None,
        skip_ratings_warning: bool = False,
    ) -> Template:
        if show_without_results is not None:
            SessionPairingsShowWithoutResults(request).set(show_without_results)
        web_context = PairingsAdminWebContext(request, tournament_id, round)
        event = web_context.get_admin_event()
        if tournament := web_context.admin_tournament:
            SessionPairingsSelectedTournament(request, event).set(tournament.id)
            if admin_round := web_context.admin_round:
                SessionPairingsSelectedRound(request, tournament).set(admin_round)

        return self._admin_event_pairings_render(
            web_context, {'skip_ratings_warning': skip_ratings_warning}
        )

    @get(
        path=[
            '/event/{event_uniq_id:str}/pairing/{tournament_id:int}/{round:int}/{board_id:int}',
        ],
        name='admin-event-pairing-modal',
    )
    async def htmx_admin_pairings_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id, round, board_id)
        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'pairing',
                'board': web_context.admin_board,
            },
        )

    @get(
        path=[
            '/event/{event_uniq_id:str}/team-pairing/'
            '{tournament_id:int}/{round:int}/{team_board_id:int}',
        ],
        name='admin-event-team-pairing-modal',
    )
    async def htmx_admin_team_pairings_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_board_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id, round)
        tournament = web_context.get_admin_tournament()
        team_board = tournament.team_boards_by_id.get(team_board_id)
        if team_board is None:
            raise NotFoundException(f'Team board {team_board_id} not found.')
        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'team-pairing',
                'team_board': team_board,
            },
        )

    @delete(
        path='/team-pairing/unpair/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{team_board_id:int}',
        name='admin-pairings-unpair-team-board',
        guards=[TournamentActionGuard(AuthAction.UNPAIR_BOARD)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_unpair_team_board(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_board_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            action=PairingAction.MANUAL_UNPAIRING,
        )
        tournament = web_context.get_admin_tournament()
        team_board = tournament.team_boards_by_id.get(team_board_id)
        if team_board is None:
            raise NotFoundException(f'Team board {team_board_id} not found.')
        tournament.unpair_team_board(team_board)
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @get(
        path=[
            '/event/{event_uniq_id:str}/unpaired-modal/{tournament_id:int}/{round:int}/{player_id:int}',
        ],
        name='pairings-unpaired-player-modal',
    )
    async def htmx_pairings_unpaired_player_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request, tournament_id, round, player_id=player_id
        )
        tournament_player = web_context.get_admin_player()
        admin_tournament = web_context.get_admin_tournament()

        byes: int = 0
        for round_ in tournament_player.pairings:
            match tournament_player.pairings[round_].result:
                case Result.HALF_POINT_BYE:
                    byes += 1
                case Result.FULL_POINT_BYE:
                    byes += 2

        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'unpaired-player',
                'tournament_player': tournament_player,
                'exempt_tournament_player': next(
                    (
                        b.white_tournament_player
                        for b in web_context.admin_boards
                        if b.exempt
                    ),
                    None,
                ),
                'hpb_possible': byes < admin_tournament.max_byes,
            },
        )

    def _admin_update_result(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round_: int,
        board_id: int,
        result: int,
        trigger_event: str | None = None,
        validate_result: bool = False,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round_,
            board_id=board_id,
            action=None if validate_result else PairingAction.RESULT_UPDATE,
        )
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        board = web_context.get_admin_board()

        if board.exempt:
            return self._admin_event_pairings_render(web_context)

        target_board_id: int | None
        if result not in (Result.admin_imputable_results()):
            raise ClientException(f'Invalid result [{result}].')

        context = web_context.template_context

        if validate_result:
            if board.result != result:
                trigger_event = 'highlight_board_with_warning'
                context |= {'extra_row_class': 'highlight highlight-warning'}
                target_board_id = board_id
            else:
                target_board_id = self._next_board_id(
                    board_id, web_context.admin_filtered_boards
                )
        else:
            r = Result(result)
            if r.is_special_result:
                if message := plugin_manager.hook_for_event(
                    event, 'signal_special_result_set'
                )(tournament=tournament, result=r):
                    Message.warning(request, message)

            tournament.add_result(board, r)
            target_board_id = self._next_board_id(
                board_id, web_context.admin_filtered_boards
            )
            # Refetch the context to get the new default_print_document etc.
            context = web_context.template_context

        if not web_context.requires_refresh:
            return HTMXTemplate(
                template_name='/admin/pairings/pairing_row_and_controls.html',
                context=context
                | {
                    'messages': Message.messages(web_context.request),
                },
                re_target='#round-controls',
                re_swap='outerHTML',
                trigger_event=trigger_event,
                after='receive',
                params={'board_id': target_board_id},
            )

        return self._admin_event_pairings_render(web_context)

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
        path='/pairing/set-result/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}/{result:int}',
        name='admin-pairings-set-result',
        guards=[SetResultGuard()],
    )
    async def htmx_admin_set_result(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        board_id: int,
        result: int,
    ) -> Template:
        return self._admin_update_result(
            request,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=result,
            trigger_event='close_modal',
        )

    @delete(
        path='/pairing/unpair/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='admin-pairings-unpair-board',
        guards=[TournamentActionGuard(AuthAction.UNPAIR_BOARD)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_unpair(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            action=PairingAction.MANUAL_UNPAIRING,
        )
        board = web_context.get_admin_board()
        tournament = web_context.get_admin_tournament()
        tournament.unpair_boards([board])

        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @patch(
        path='/pairing/permute/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}',
        name='admin-pairings-permute',
        guards=[TournamentActionGuard(AuthAction.PERMUTE_BOARD)],
    )
    async def htmx_admin_permute(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        board_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            action=PairingAction.COLOR_PERMUTE,
        )
        board = web_context.get_admin_board()
        board.permute_colors()
        return self._admin_event_pairings_render(web_context)

    @put(
        path='/pairing/set-result-hotkey/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-set-result-hotkey',
        guards=[TournamentActionGuard(AuthAction.UPDATE_RESULTS)],
        data=Body(media_type=RequestEncodingType.URL_ENCODED),
    )
    async def htmx_admin_set_result_hotkey(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        board_id: int = int(data['board_id'])
        key: str = data['key']
        result: Optional[Result] = None
        match key:
            case 'Digit0' | 'Numpad0':
                result = Result.NO_RESULT
            case 'Digit1' | 'Numpad1':
                result = Result.WIN
            case 'Digit2' | 'Numpad2':
                result = Result.LOSS
            case 'Digit3' | 'Numpad3':
                result = Result.DRAW
            case _:
                return HTMXTemplate(
                    template_name='/common/empty.html',
                    re_swap='none',
                )
        assert result is not None
        return self._admin_update_result(
            request,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
            result=result,
            validate_result=data['validate_result'] == 'true',
        )

    @patch(
        path=(
            '/pairing/swap-board-player/{event_uniq_id:str}/{tournament_id:int}'
            '/{round:int}/{board_id:int}/{side:str}'
        ),
        name='admin-pairings-swap-board-player',
        guards=[TournamentActionGuard(AuthAction.UPDATE_RESULTS)],
        data=Body(media_type=RequestEncodingType.URL_ENCODED),
    )
    async def htmx_admin_swap_board_player(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        board_id: int,
        side: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        if side not in ('W', 'B'):
            raise ClientException(f'Invalid side [{side}].')
        this_side: str = 'white' if side == 'W' else 'black'
        try:
            new_player_id = int(data.get('new_player_id', '0') or '0')
        except ValueError:
            raise ClientException('Invalid new_player_id.')

        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            board_id=board_id,
        )
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        this_board = web_context.get_admin_board()

        if not event.is_team_event:
            raise ClientException('Lineup swap only allowed in team events.')

        team_board_id = this_board.stored_board.team_board_id
        if team_board_id is None:
            raise ClientException('Board is not part of a team match.')
        team_board = tournament.team_boards_by_id[team_board_id]

        side_team = self._team_owning_side(
            tournament, team_board, this_board.index, side
        )
        if side_team is None:
            raise ClientException('Cannot determine team for this side at this slot.')

        old_player_id = (
            this_board.stored_board.white_player_id
            if this_side == 'white'
            else this_board.stored_board.black_player_id
        )

        # Punch a hole.
        if new_player_id == 0:
            if old_player_id is None:
                return self._admin_event_pairings_render(web_context)
            self._punch_lineup_hole_for_team(
                event, tournament, this_board, team_board, side_team, old_player_id
            )
            return self._admin_event_pairings_render(web_context)

        # Fill a hole.
        if old_player_id is None:
            new_tp = tournament.tournament_players_by_id.get(new_player_id)
            if new_tp is None or new_tp.team_id != side_team.id:
                raise ClientException('Picked player is not in this team.')
            self._fill_lineup_hole(
                event,
                tournament,
                this_board,
                team_board,
                side_team,
                this_side,
                new_tp,
            )
            return self._admin_event_pairings_render(web_context)

        new_player = event.players_by_id.get(new_player_id)
        if new_player is None or new_player.team_id != side_team.id:
            raise ClientException('New player is not in this team.')

        if old_player_id == new_player_id:
            return self._admin_event_pairings_render(web_context)

        # Locate the new player on another board of this team match
        # (they're already in the lineup; the dropdown's "Bench"
        # branch is what the hole-fill path handles).
        other_board: Board | None = None
        for board in team_board.boards:
            if board.identifier == this_board.identifier:
                continue
            if (
                board.stored_board.white_player_id == new_player_id
                or board.stored_board.black_player_id == new_player_id
            ):
                other_board = board
                break
        if other_board is None:
            raise ClientException('New player is not currently in this team match.')

        new_player_tp = tournament.tournament_players_by_id[new_player_id]
        # Vacate both slots, then drop the new player into the chosen
        # one. The displaced (old) player leaves the round lineup
        # entirely; the source slot becomes a hole.
        self._punch_lineup_hole_for_team(
            event, tournament, this_board, team_board, side_team, old_player_id
        )
        self._punch_lineup_hole_for_team(
            event, tournament, other_board, team_board, side_team, new_player_id
        )
        self._fill_lineup_hole(
            event,
            tournament,
            this_board,
            team_board,
            side_team,
            this_side,
            new_player_tp,
        )
        return self._admin_event_pairings_render(web_context)

    @staticmethod
    def _team_owning_side(
        tournament: Tournament,
        team_board: TeamBoard,
        slot: int,
        side: str,
    ) -> Team | None:
        """Which team owns physical side ``side`` ('W' / 'B') at
        board ``slot`` of ``team_board``. Determined entirely by the
        tournament's colour pattern at this slot."""
        if team_board.team_b is None:
            return None
        pattern = tournament.color_pattern or ''
        if 0 <= slot < len(pattern):
            team_a_color = pattern[slot]
        else:
            team_a_color = 'W' if slot % 2 == 0 else 'B'
        team_a_is_white = team_a_color == 'W'
        a_or_b_is_white = team_a_is_white if side == 'W' else not team_a_is_white
        return team_board.team_a if a_or_b_is_white else team_board.team_b

    @staticmethod
    def _punch_lineup_hole_for_team(
        event: Event,
        tournament: Tournament,
        this_board: Board,
        team_board: TeamBoard,
        side_team: Team,
        side_player_id: int,
    ) -> None:
        """Remove ``side_team``'s player from this board's slot.
        Leaves an index gap in the team's lineup. The physical side
        the player was on becomes ``NULL`` on the board (no flip).
        Both sides empty ⇒ delete the board."""
        round_ = this_board.round
        slot = this_board.index
        w_id = this_board.stored_board.white_player_id
        physical_side: str = 'white' if side_player_id == w_id else 'black'
        side_tp = tournament.tournament_players_by_id[side_player_id]
        with EventDatabase(event.uniq_id, write=True) as database:
            lineup_slots: list[int | None] = [
                p.id if p is not None else None
                for p in side_team.effective_round_slots(round_)
            ]
            if 0 <= slot < len(lineup_slots):
                lineup_slots[slot] = None
            side_team.set_round_lineup(round_, lineup_slots, database)
            side_pairing = side_tp.pairings_by_round[round_]
            # Update (don't delete) the pairing: the
            # ``delete_board_on_pairing_delete`` trigger would
            # otherwise nuke this slot's board (cascading to the
            # opponent's pairing too). Clearing ``board_id`` first
            # lets the player look "unpaired" without losing the slot.
            side_pairing.stored_pairing.result = Result.NO_RESULT.value
            side_pairing.stored_pairing.board_id = None
            side_pairing.stored_pairing.effective_points = None
            side_pairing.stored_pairing.illegal_moves = 0
            side_pairing.update(database)
            if physical_side == 'white':
                this_board.stored_board.white_player_id = None
                this_board._white_player_ref = None
            else:
                this_board.stored_board.black_player_id = None
                this_board._black_player_ref = None
            # Keep the board even when both sides become empty so the
            # slot remains visible in the team block and can be
            # re-filled from either team.
            database.update_stored_board(this_board.stored_board)
            opp_id = (
                this_board.stored_board.black_player_id
                if physical_side == 'white'
                else this_board.stored_board.white_player_id
            )
            if opp_id is not None:
                opp_tp = tournament.tournament_players_by_id[opp_id]
                opp_pairing = opp_tp.pairings_by_round[round_]
                # Opposing player now has no opponent → forfeit win,
                # mirroring the lineup-hole branch in ``create_boards``.
                opp_pairing.stored_pairing.result = Result.FORFEIT_WIN.value
                opp_pairing.stored_pairing.effective_points = None
                opp_pairing.stored_pairing.illegal_moves = 0
                opp_pairing.update(database)
            this_board.set_last_result_update(Result.NO_RESULT, database)

    @staticmethod
    def _fill_lineup_hole(
        event: Event,
        tournament: Tournament,
        this_board: Board,
        team_board: TeamBoard,
        side_team: Team,
        physical_side: str,
        new_player_tp: 'TournamentPlayer',
    ) -> None:
        """Put ``new_player_tp`` on the ``physical_side`` of
        ``this_board`` (its current value must be ``NULL`` — a hole)
        and add the player to ``side_team``'s round lineup at this
        slot. No swap, no reshape: the chip-colour matches the
        physical side everywhere."""
        round_ = this_board.round
        slot = this_board.index
        with EventDatabase(event.uniq_id, write=True) as database:
            lineup_slots: list[int | None] = [
                p.id if p is not None else None
                for p in side_team.effective_round_slots(round_)
            ]
            if 0 <= slot < len(lineup_slots):
                lineup_slots[slot] = new_player_tp.id
            side_team.set_round_lineup(round_, lineup_slots, database)
            this_board.replace_player(
                new_player_tp,
                physical_side,  # type: ignore[arg-type]
            )
            database.update_stored_board(this_board.stored_board)
            new_pairing = new_player_tp.pairings_by_round[round_]
            new_pairing.stored_pairing.result = Result.NO_RESULT.value
            new_pairing.stored_pairing.board_id = this_board.identifier
            new_pairing.stored_pairing.effective_points = None
            new_pairing.stored_pairing.illegal_moves = 0
            new_pairing.update(database)
            opp_id = (
                this_board.stored_board.black_player_id
                if physical_side == 'white'
                else this_board.stored_board.white_player_id
            )
            if opp_id is not None:
                opp_tp = tournament.tournament_players_by_id[opp_id]
                opp_pairing = opp_tp.pairings_by_round[round_]
                opp_pairing.stored_pairing.result = Result.NO_RESULT.value
                opp_pairing.stored_pairing.effective_points = None
                opp_pairing.stored_pairing.illegal_moves = 0
                opp_pairing.update(database)
            this_board.set_last_result_update(Result.NO_RESULT, database)

    @patch(
        path=(
            '/pairings-player-check-in-out/{event_uniq_id:str}/{tournament_id:int}'
            '/{round:int}/{player_id:int}'
        ),
        name='pairings-player-check-in-out',
        guards=[TournamentActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_pairings_player_check_in_out(
        self,
        request: HTMXRequest,
        channels: ChannelsPlugin,
        tournament_id: int,
        player_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            player_id=player_id,
            round_=round,
        )
        player = web_context.get_admin_player()
        tournament = player.single_tournament
        tournament.check_in_player(player, not player.check_in)
        PlayerAdminController.publish_new_checkin(channels, tournament)
        message = _('Player [{player}] marked as "{status}".').format(
            player=player.full_name,
            status=_('Present') if player.check_in else _('Absent'),
        )
        Message.success(request, message)
        web_context.reload_unpaired_player_lists()
        return self._admin_event_pairings_render(web_context)

    @patch(
        path=(
            '/pairings-player-return-to-tournament/{event_uniq_id:str}/{tournament_id:int}'
            '/{round:int}/{player_id:int}'
        ),
        name='pairings-player-return-to-tournament',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_pairings_player_return_to_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
        player_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            player_id=player_id,
            round_=round,
        )
        player = web_context.get_admin_player()
        tournament = player.single_tournament
        tournament.set_player_participation(player)
        message = _('Player [{player}] has returned to the tournament.').format(
            player=player.full_name
        )
        Message.success(request, message)
        web_context.reload_unpaired_player_lists()
        return self._admin_event_pairings_render(web_context)

    @patch(
        path=(
            '/pairings/set-player-zpb/{event_uniq_id:str}/'
            '{tournament_id:int}/{player_id:int}/{round:int}'
        ),
        name='pairings-set-player-zpb',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_set_player_zpb(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            player_id=player_id,
            action=PairingAction.BYE_UPDATE,
        )
        tournament = web_context.get_admin_tournament()
        player = web_context.get_admin_player()
        tournament.set_player_byes(player, {round: Result.ZERO_POINT_BYE})
        message = _('Zero-Point Bye attributed to player [{player}].').format(
            player=player.full_name
        )
        Message.success(request, message)
        web_context.reload_unpaired_player_lists()
        return self._admin_event_pairings_render(web_context)

    @patch(
        path=(
            '/pairings/set-player-hpb/{event_uniq_id:str}/'
            '{tournament_id:int}/{player_id:int}/{round:int}'
        ),
        name='pairings-set-player-hpb',
        guards=[TournamentActionGuard(AuthAction.SET_HPB)],
    )
    async def htmx_set_player_hpb(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            player_id=player_id,
            action=PairingAction.BYE_UPDATE,
        )
        tournament = web_context.get_admin_tournament()
        player = web_context.get_admin_player()
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
                    player_name=player.full_name
                ),
            )
            return self._admin_event_pairings_render(web_context)
        message = _('Half-Point Bye attributed to player [{player}].').format(
            player=player.full_name
        )
        tournament.set_player_byes(player, {round: Result.HALF_POINT_BYE})
        Message.success(request, message)
        web_context.reload_unpaired_player_lists()
        return self._admin_event_pairings_render(web_context)

    @patch(
        path=(
            '/pairings/cancel-player-bye/{event_uniq_id:str}/'
            '{tournament_id:int}/{player_id:int}/{round:int}'
        ),
        name='pairings-cancel-player-bye',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_cancel_bye(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            player_id=player_id,
            action=PairingAction.BYE_UPDATE,
        )
        tournament = web_context.get_admin_tournament()
        player = web_context.get_admin_player()
        tournament.set_player_byes(player, {round: Result.NO_RESULT})
        message = _('Player [{player}] has returned for this round.').format(
            player=player.full_name
        )
        Message.success(request, message)
        web_context.reload_unpaired_player_lists()
        return self._admin_event_pairings_render(web_context)

    @get(
        path=[
            '/event/{event_uniq_id:str}/unpaired-team-modal/'
            '{tournament_id:int}/{round:int}/{team_id:int}',
        ],
        name='pairings-unpaired-team-modal',
    )
    async def htmx_pairings_unpaired_team_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id, round)
        admin_tournament = web_context.get_admin_tournament()
        team = admin_tournament.event.teams_by_id.get(team_id)
        if team is None:
            raise NotFoundException(f'Team {team_id} not found.')
        exempt_team_board = next(
            (
                tb
                for tb in admin_tournament.get_round_team_boards(round)
                if tb.stored_team_board.team_b_id is None
                and tb.stored_team_board.bye_type not in ('HPB', 'FPB', 'ZPB')
            ),
            None,
        )
        exempt_team = (
            exempt_team_board.team_a
            if exempt_team_board is not None
            and exempt_team_board.stored_team_board.team_a_id != team_id
            else None
        )
        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'unpaired-team',
                'admin_team': team,
                'admin_team_bye_type': team.round_bye_type(round),
                'exempt_team': exempt_team,
            },
        )

    def _set_team_bye(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
        bye_type: str | None,
        success_message: str,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            action=PairingAction.BYE_UPDATE,
        )
        admin_tournament = web_context.get_admin_tournament()
        team = admin_tournament.event.teams_by_id.get(team_id)
        if team is None:
            raise NotFoundException(f'Team {team_id} not found.')
        with EventDatabase(admin_tournament.event.uniq_id, write=True) as db:
            team.set_round_bye(round, bye_type, db)
        Message.success(request, success_message.format(team=team.name))
        web_context.reload_unpaired_team_lists()
        return self._admin_event_pairings_render(web_context)

    @patch(
        path=(
            '/pairings/set-team-zpb/{event_uniq_id:str}/'
            '{tournament_id:int}/{team_id:int}/{round:int}'
        ),
        name='pairings-set-team-zpb',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_set_team_zpb(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
    ) -> Template:
        return self._set_team_bye(
            request,
            tournament_id,
            round,
            team_id,
            'ZPB',
            _('Zero-Point Bye attributed to team [{team}].'),
        )

    @patch(
        path=(
            '/pairings/set-team-hpb/{event_uniq_id:str}/'
            '{tournament_id:int}/{team_id:int}/{round:int}'
        ),
        name='pairings-set-team-hpb',
        guards=[TournamentActionGuard(AuthAction.SET_HPB)],
    )
    async def htmx_set_team_hpb(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
    ) -> Template:
        return self._set_team_bye(
            request,
            tournament_id,
            round,
            team_id,
            'HPB',
            _('Half-Point Bye attributed to team [{team}].'),
        )

    @patch(
        path=(
            '/pairings/set-team-fpb/{event_uniq_id:str}/'
            '{tournament_id:int}/{team_id:int}/{round:int}'
        ),
        name='pairings-set-team-fpb',
        guards=[TournamentActionGuard(AuthAction.SET_HPB)],
    )
    async def htmx_set_team_fpb(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
    ) -> Template:
        return self._set_team_bye(
            request,
            tournament_id,
            round,
            team_id,
            'FPB',
            _('Full-Point Bye attributed to team [{team}].'),
        )

    @patch(
        path=(
            '/pairings/cancel-team-bye/{event_uniq_id:str}/'
            '{tournament_id:int}/{team_id:int}/{round:int}'
        ),
        name='pairings-cancel-team-bye',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_cancel_team_bye(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
    ) -> Template:
        return self._set_team_bye(
            request,
            tournament_id,
            round,
            team_id,
            None,
            _('Team [{team}] has returned for this round.'),
        )

    @patch(
        path=(
            '/pairings/pair-team/{event_uniq_id:str}/'
            '{tournament_id:int}/{team_id:int}/{round:int}'
        ),
        name='admin-pairings-pair-team',
        guards=[TournamentActionGuard(AuthAction.MANUALLY_PAIR_PLAYERS)],
    )
    async def htmx_admin_pair_team(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        team_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            action=PairingAction.MANUAL_PAIRING,
        )
        pairing_round = web_context.admin_round or 1
        tournament = web_context.get_admin_tournament()
        team = tournament.event.teams_by_id.get(team_id)
        if team is None:
            raise NotFoundException(f'Team {team_id} not found.')
        exempt_team_board = next(
            (
                tb
                for tb in tournament.get_round_team_boards(pairing_round)
                if tb.stored_team_board.team_b_id is None
                and tb.stored_team_board.bye_type not in ('HPB', 'FPB', 'ZPB')
            ),
            None,
        )
        exempt_team = (
            exempt_team_board.team_a
            if exempt_team_board is not None
            and exempt_team_board.stored_team_board.team_a_id != team.id
            else None
        )
        tb = tournament.create_team_round_pairing(pairing_round, team.id)
        if exempt_team is not None:
            message = _(
                'Team [{team}] has been paired against [{opponent}] at board #{board}.'
            ).format(team=team.name, opponent=exempt_team.name, board=tb.index + 1)
        else:
            message = _('Pairing-Allocated Bye assigned to team [{team}].').format(
                team=team.name
            )
        Message.success(request, message)
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @patch(
        path=(
            '/pairings/pair-player/{event_uniq_id:str}/'
            '{tournament_id:int}/{player_id:int}/{round:int}'
        ),
        name='admin-pairings-pair-player',
        guards=[TournamentActionGuard(AuthAction.MANUALLY_PAIR_PLAYERS)],
    )
    async def htmx_admin_pair_player(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            player_id=player_id,
            action=PairingAction.MANUAL_PAIRING,
        )
        pairing_round = web_context.admin_round or 1
        tournament = web_context.get_admin_tournament()
        tournament_player = web_context.get_admin_player()
        exempt_tournament_player = next(
            (b.white_tournament_player for b in web_context.admin_boards if b.exempt),
            None,
        )
        if exempt_tournament_player is not None:
            board = tournament.create_round_pairing(
                pairing_round,
                exempt_tournament_player.id,
                tournament_player.id,
            )
            message = _(
                'Player [{player}] has been paired against '
                '[{opponent}] at board #{board}.'
            ).format(
                player=tournament_player.full_name,
                opponent=exempt_tournament_player.full_name,
                board=board.number,
            )
        else:
            tournament.create_round_pairing(
                pairing_round,
                tournament_player.id,
                None,
            )
            message = _('Pairing-Allocated Bye assigned to player [{player}].').format(
                player=tournament_player.full_name
            )
        Message.success(request, message)
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            player_id=tournament_player.id,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @post(
        path='/pairings/set-all-present/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='pairings-set-all-present',
        guards=[TournamentActionGuard(AuthAction.USE_PAIRING_ENGINE)],
    )
    async def htmx_pairings_set_all_present(
        self,
        channels: ChannelsPlugin,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
        )
        tournament = web_context.get_admin_tournament()
        tournament.check_in_all_players(True)
        PlayerAdminController.publish_new_checkin(channels, tournament)
        Message.success(request, _('All players marked as "Present".'))
        web_context.reload_unpaired_player_lists()
        return self._admin_event_pairings_render(web_context)

    def _generate_round_pairings(
        self, web_context: PairingsAdminWebContext
    ) -> Template:
        tournament = web_context.get_admin_tournament()
        round_ = web_context.admin_round
        request = web_context.request
        if error := tournament.generate_round_pairings(round_):
            Message.error(request, error)
        else:
            Message.success(request, _('Pairings successfully generated.'))
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament.id,
            round_=round_,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @post(
        path='/pairings/generate/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='generate-round-pairings',
        guards=[TournamentActionGuard(AuthAction.USE_PAIRING_ENGINE)],
    )
    async def htmx_generate_round_pairings(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            action=PairingAction.FULL_PAIRING,
        )
        tournament = web_context.get_admin_tournament()
        tournament.set_valid_pairing_settings()
        return self._generate_round_pairings(web_context)

    @post(
        path='/pairings/generate-partial/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='generate-round-partial-pairings',
        guards=[TournamentActionGuard(AuthAction.USE_PAIRING_ENGINE)],
    )
    async def htmx_generate_round_partial_pairings(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            action=PairingAction.PARTIAL_PAIRING,
        )
        tournament = web_context.get_admin_tournament()
        tournament.set_valid_pairing_settings()
        round_ = web_context.admin_round
        if error := tournament.pairing_variation.engine.generate_pairings(
            tournament, round_, True
        ):
            Message.error(request, error)
        else:
            unpaired_count = sum(
                player.pairings[round_].needs_pairing
                for player in tournament.tournament_players
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

        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @post(
        path='/pairings/generate/{event_uniq_id:str}/{tournament_id:int}',
        name='generate-tournament-pairings',
        guards=[TournamentActionGuard(AuthAction.USE_PAIRING_ENGINE)],
    )
    async def htmx_generate_tournament_pairings(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id=tournament_id)
        tournament = web_context.get_admin_tournament()

        if errors := tournament.get_pairing_settings_data_errors(data):
            return self._render_pairings_settings_modal(web_context, data, errors)

        self._save_pairing_settings_data(tournament, data)
        error: str = ''
        for round_ in range(1, tournament.rounds + 1):
            if error := tournament.pairing_variation.engine.generate_pairings(
                tournament, round_
            ):
                break
        if error:
            Message.error(request, error)
        else:
            tournament.set_current_round(1)
            Message.success(
                request,
                _(
                    'Pairings generated for all rounds of tournament [{tournament}].'
                ).format(tournament=tournament.name),
            )

        web_context = PairingsAdminWebContext(
            request, tournament_id=tournament_id, reload_event=True
        )
        return self._admin_event_pairings_render(web_context)

    @post(
        path='/pairings/unpair/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-unpair-round',
        guards=[TournamentActionGuard(AuthAction.UNPAIR_ROUND)],
    )
    async def admin_pairings_unpair(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            action=PairingAction.FULL_UNPAIRING,
        )
        tournament = web_context.get_admin_tournament()
        tournament.unpair_boards(web_context.admin_boards)

        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            reload_event=True,
        )
        return self._admin_event_pairings_render(web_context)

    @post(
        path='/pairings/unpair-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-pairings-unpair-tournament',
        guards=[TournamentActionGuard(AuthAction.UNPAIR_ROUND)],
    )
    async def admin_pairings_unpair_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id=tournament_id)
        tournament = web_context.get_admin_tournament()
        tournament.unpair_boards(list(tournament.boards_by_id.values()))
        tournament.set_current_round(0)

        web_context = PairingsAdminWebContext(
            request, tournament_id=tournament_id, reload_event=True
        )
        return self._admin_event_pairings_render(web_context)

    @get(
        path=(
            '/pairings/safety-mode-modal/{event_uniq_id:str}/{tournament_id:int}'
            '/{round:int}/{action:str}/{redirect_method:str}/{redirect_route:path}'
        ),
        name='admin-pairings-safety-mode-modal',
    )
    async def admin_pairings_safety_mode_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        action: str,
        redirect_method: str,
        redirect_route: str,
    ) -> Template:
        try:
            protected_action = PairingAction(action)
        except ValueError:
            raise NotFoundException(f'Unknown pairing action [{action}]')
        web_context = PairingsAdminWebContext(request, tournament_id, round)
        tournament = web_context.get_admin_tournament()
        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'safety-mode',
                'action': protected_action,
                'required_mode': (
                    tournament.pairing_system.permission_handler.required_mode(
                        web_context.round_status, protected_action
                    )
                ),
                'redirect_method': redirect_method,
                'redirect_route': redirect_route,
            },
        )

    @post(
        path=[
            '/pairings/update-safety-mode/'
            '{event_uniq_id:str}/{tournament_id:int}/{round:int}',
            '/pairings/update-safety-mode/{event_uniq_id:str}'
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
        tournament_id: int,
        round: int,
    ) -> Template:
        mode = WebContext.form_data_to_str(data, 'mode') or ''
        try:
            SessionPairingsSafetyMode(request).set(SafetyMode(mode))
        except ValueError:
            raise NotFoundException(f'Unknown safety mode [{mode}]')
        web_context = PairingsAdminWebContext(request, tournament_id, round)
        return self._admin_event_pairings_render(web_context)

    @get(
        path='/pairings/unfinished-round-modal/'
        '{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-unfinished-round-modal',
    )
    async def admin_pairings_unfinished_round_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
        )

        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'unfinished-round',
                'unpaired_count': len(web_context.admin_unpaired),
                'absent_count': len(web_context.admin_absent_players),
                'no_result_board_count': len(
                    [
                        board
                        for board in web_context.admin_boards
                        if board.result == Result.NO_RESULT
                    ]
                ),
            },
        )

    @get(
        path='/pairings/ratings-warning-modal/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='pairings-ratings-warning-modal',
    )
    async def htmx_pairings_ratings_warning_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id, round)

        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'pairing-ratings-warning',
                'data_sources': DataSourceManager().objects(),
            },
        )

    @get(
        path='/pairings/absents-modal/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='pairings-absents-modal',
    )
    async def htmx_pairings_absents_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request, tournament_id, round, load_check_in_data=True
        )
        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'pairing-absents',
            },
        )

    @classmethod
    def _render_pairings_settings_modal(
        cls,
        web_context: PairingsAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        tournament = web_context.get_admin_tournament()
        if data is None:
            data = {}
            for setting in tournament.pairing_variation.settings:
                data |= setting.get_form_data(tournament)
            errors = tournament.get_pairing_settings_data_errors(data)

        template_context = {
            'modal': 'pairing-settings',
            'pairing_settings': tournament.pairing_variation.settings,
            'data': data,
            'errors': errors or {},
        }
        return cls._admin_event_pairings_render(web_context, template_context)

    @get(
        path='/pairings/settings-modal/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='pairings-settings-modal',
    )
    async def htmx_pairings_settings_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id, round)
        return self._render_pairings_settings_modal(web_context)

    @post(
        path='/pairings/generate-with-settings/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='generate-round-pairings-with-settings',
        guards=[TournamentActionGuard(AuthAction.USE_PAIRING_ENGINE)],
    )
    async def htmx_generate_round_pairings_with_settings(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
        )
        tournament = web_context.get_admin_tournament()
        if errors := tournament.get_pairing_settings_data_errors(data):
            return self._render_pairings_settings_modal(web_context, data, errors)

        self._save_pairing_settings_data(tournament, data)
        return self._generate_round_pairings(web_context)

    @staticmethod
    def _save_pairing_settings_data(tournament: Tournament, data: dict[str, str]):
        stored_settings: dict[str, Any] = {}
        for setting in tournament.pairing_variation.settings:
            stored_settings[setting.id] = setting.to_stored_value(
                setting.from_form_data(data)
            )
        tournament.update_pairing_settings(stored_settings)

    @post(
        path='/pairings/validate-absents/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='pairings-validate-absents',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_pairings_validate_absents(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
            load_check_in_data=True,
        )
        tournament = web_context.get_admin_tournament()
        for player in web_context.admin_absent_players:
            match data.get(f'player_{player.id}'):
                case 'zpb':
                    tournament.set_player_byes(player, {round: Result.ZERO_POINT_BYE})
                case 'withdraw':
                    tournament.set_player_participation(player, withdraw=True)
                case 'present':
                    tournament.check_in_player(player, check_in=True)
        if round == 1:
            return self._render_pairings_settings_modal(web_context)
        return self._generate_round_pairings(web_context)

    @put(
        path='/tournament/set-current-round/{event_uniq_id:str}/{tournament_id:int}/{current_round:int}',
        name='admin-tournament-set-current-round',
        guards=[TournamentActionGuard(AuthAction.SET_CURRENT_ROUND)],
    )
    async def htmx_admin_tournament_set_current_round(
        self,
        request: HTMXRequest,
        tournament_id: int,
        current_round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=current_round,
        )
        tournament = web_context.get_admin_tournament()
        tournament.set_current_round(round_=current_round)
        SessionPairingsSelectedRound(request, tournament).set(current_round)
        return self._admin_event_pairings_render(web_context)

    @put(
        path='/tournament/add-illegal-move/{event_uniq_id:str}/{tournament_id:int}/{round:int}/{player_id:int}',
        name='admin-tournament-add-illegal-move',
        guards=[TournamentActionGuard(AuthAction.SET_ILLEGAL_MOVES)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tournament_add_illegal_move(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            player_id=player_id,
            round_=round,
        )
        tournament = web_context.get_admin_tournament()
        tournament_player = web_context.get_admin_player()
        tournament.store_illegal_move(tournament_player)
        return self._admin_event_pairings_render(
            web_context=web_context,
        )

    @delete(
        path='/tournament/delete-illegal-move/{event_uniq_id:str}/{tournament_id:int}/{round:int}/{player_id:int}',
        name='admin-tournament-delete-illegal-move',
        guards=[TournamentActionGuard(AuthAction.SET_ILLEGAL_MOVES)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tournament_delete_illegal_move(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
        player_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            player_id=player_id,
            round_=round,
        )
        tournament = web_context.get_admin_tournament()
        tournament_player = web_context.get_admin_player()
        tournament.delete_illegal_move(tournament_player)
        return self._admin_event_pairings_render(
            web_context=web_context,
        )

    @get(
        path='/pairings/needs-refresh-message/{event_uniq_id:str}/{tournament_id:int}/{round:int}/{reason:str}',
        name='pairings-needs-refresh-message',
    )
    async def htmx_pairings_refresh_message(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
        reason: str,
        ignore: bool = False,
    ) -> Template:
        if ignore:
            return HTMXTemplate(template_name='/common/empty.html')
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

    @get(
        path=(
            '/pairings/absents-modal/new-check-ins-message/'
            '{event_uniq_id:str}/{tournament_id:int}/{round:int}'
        ),
        name='absents-modal-new-check-ins-message',
    )
    async def htmx_absents_modal_new_check_ins_message(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
        )
        return HTMXTemplate(
            template_name='/admin/pairings/absents_new_check_ins_alert.html',
            context=web_context.template_context,
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
                'event': f'new-user-results|{event_uniq_id}|{tournament_id}|{round_}',
                'data': '',
            },
            ['ws'],
        )
        channels.publish(
            {
                'event': f'new-user-results|{event_uniq_id}',
                'data': '',
            },
            ['ws'],
        )

    @get(
        path='/pairings/info-modal/{event_uniq_id:str}/{tournament_id:int}/{round:int}',
        name='admin-pairings-info-modal',
    )
    async def admin_pairings_info_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        round: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(
            request,
            tournament_id=tournament_id,
            round_=round,
        )
        tournament = web_context.get_admin_tournament()

        engine = tournament.pairing_variation.engine
        assert isinstance(engine, BbpPairings)

        warning: str | None = None
        (history, boards) = engine.get_history(tournament=tournament, round_=round)
        if tournament.round_has_pairings(round) and engine.pairings_diff(
            tournament, round, ignore_order=False, expected_stored_boards=boards
        ):
            warning = _(
                'Current pairings differ from the expected Swiss pairings, '
                'possibly due to manual changes, complementary pairings, '
                'or renumbering after rating/late-entry adjustments.'
            )

        buckets: dict[float, list[TournamentHistoryPlayer]] = defaultdict(list)

        # Put each player in the right bucket
        for player in history.players:
            buckets[player.points].append(player)

        # Sort players within each bucket by player id
        for pts, players in buckets.items():
            players.sort(key=lambda p: p.id)

        # Create grouped list
        grouped = [(pts, players) for pts, players in buckets.items()]

        # Sort groups by points (highest first)
        grouped.sort(key=lambda it: it[0], reverse=True)

        return self._admin_event_pairings_render(
            web_context,
            {
                'modal': 'pairing_info',
                'pairing_history': grouped,
                'players_by_pairing_number': tournament.tournament_players_by_pairing_number,
                'warning': warning,
            },
        )

    @patch(
        path='/manual-tiebreak/update/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-manual-tiebreak-update',
    )
    async def htmx_admin_manual_tiebreak_update(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id=tournament_id)

        tournament = web_context.get_admin_tournament()

        player_data = data['player']
        ordered_player_ids: list[int] = (
            player_data if isinstance(player_data, list) else []
        )

        # Group players by manual_rank_key, preserving current order
        by_rank: dict[object, list[TournamentPlayer]] = defaultdict(list)
        for tournament_player in sorted(
            tournament.tournament_players, key=attrgetter('rank'), reverse=True
        ):
            by_rank[tournament_player.before_manual_rank_key].append(tournament_player)

        players_to_update: dict[int, int | None] = {}

        #  Update manual_tiebreaks: assign only to point groups whose index varies from the natural sort order, clear for others
        for group in by_rank.values():
            # Singletons never need manual tiebreak
            if len(group) <= 1:
                for tournament_player in group:
                    if tournament_player.manual_tiebreak is not None:
                        players_to_update[tournament_player.id] = None
                continue

            # Current order (by manual_rank_key) and submitted order (restricted to this group)
            current_group_ids = [tournament_player.id for tournament_player in group][
                ::-1
            ]

            new_group_ids = [
                pid for pid in ordered_player_ids if pid in current_group_ids
            ]
            # Ignore groups that have not been modified
            if current_group_ids == new_group_ids:
                continue

            # Maps of index within the group
            for index, player_id in enumerate(new_group_ids):
                players_to_update[player_id] = len(group) - index

        if players_to_update:
            with EventDatabase(tournament.event.uniq_id, True) as database:
                database.set_tournament_players_manual_tiebreak(
                    tournament_id, players_to_update
                )

        web_context = PairingsAdminWebContext(
            request, tournament_id=tournament_id, reload_event=True
        )

        # Re-render the admin pairings view
        return self._admin_event_pairings_render(web_context)

    @post(
        path='/manual-tiebreak/reset/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-manual-tiebreak-reset',
    )
    async def htmx_admin_manual_tiebreak_reset(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template:
        web_context = PairingsAdminWebContext(request, tournament_id=tournament_id)
        tournament = web_context.get_admin_tournament()
        with EventDatabase(event_uniq_id, True) as database:
            tournament.delete_manual_tie_break_values(database)
        web_context = PairingsAdminWebContext(
            request, tournament_id=tournament_id, reload_event=True
        )
        return self._admin_event_pairings_render(web_context)
