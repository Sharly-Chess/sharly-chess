from litestar.exceptions import (
    NotFoundException,
    ClientException,
)
from litestar_htmx import HTMXRequest

from common.exception import SharlyChessException
from data.auth.client import Client
from data.board import Board
from data.display_controller import DisplayController
from data.event import Event
from data.loader import EventLoader
from data.player import Player
from data.rotator import Rotator
from data.screen import Screen
from data.tournament import Tournament
from utils.enum import Result


class RequestUtils:
    REQUEST_EVENT_ATTR: str = 'sharly_chess_event'
    EVENT_UNIQ_ID_PARAM: str = 'event_uniq_id'

    @classmethod
    def _get_event(
        cls,
        request: HTMXRequest,
        optional: bool,
    ) -> Event | None:
        """Returns the event of the request (stored in the state of the request)."""
        if cls.REQUEST_EVENT_ATTR not in request.state:
            request.state[cls.REQUEST_EVENT_ATTR] = None
            if cls.EVENT_UNIQ_ID_PARAM in request.path_params:
                event_uniq_id: str = request.path_params[cls.EVENT_UNIQ_ID_PARAM]
                try:
                    request.state[cls.REQUEST_EVENT_ATTR] = EventLoader.get(
                        request
                    ).load_event(event_uniq_id)
                except SharlyChessException as sce:
                    raise NotFoundException(
                        f'Event [{event_uniq_id}] not found.'
                    ) from sce
        if not optional and request.state[cls.REQUEST_EVENT_ATTR] is None:
            raise ClientException(
                f'Path parameter [{cls.EVENT_UNIQ_ID_PARAM}] not found.'
            )
        return request.state[cls.REQUEST_EVENT_ATTR]

    @classmethod
    def get_optional_event(
        cls,
        request: HTMXRequest,
    ) -> Event | None:
        """Returns the event of the request, optional (stored in the state of the request)."""
        return cls._get_event(request, optional=True)

    @classmethod
    def get_event(
        cls,
        request: HTMXRequest,
    ) -> Event:
        """Returns the event of the request, required (stored in the state of the request)."""
        event: Event | None = cls._get_event(request, optional=False)
        assert event is not None
        return event

    REQUEST_CLIENT_ATTR: str = 'sharly_chess_client'

    @classmethod
    def get_client(
        cls,
        request: HTMXRequest,
    ) -> Client:
        """Returns the client of the request (stored in the state of the request)."""
        if cls.REQUEST_CLIENT_ATTR not in request.state:
            request.state[cls.REQUEST_CLIENT_ATTR] = Client(
                request, cls.get_optional_event(request)
            )
        return request.state[cls.REQUEST_CLIENT_ATTR]

    REQUEST_SCREEN_ATTR: str = 'sharly_chess_screen'
    SCREEN_UNIQ_ID_PARAM: str = 'screen_uniq_id'

    @classmethod
    def get_screen(
        cls,
        request: HTMXRequest,
    ) -> Screen:
        """Returns the screen of the request, required (stored in the state of the request)."""
        if cls.REQUEST_SCREEN_ATTR not in request.state:
            if cls.SCREEN_UNIQ_ID_PARAM not in request.path_params:
                raise ClientException(
                    f'Path parameter [{cls.SCREEN_UNIQ_ID_PARAM}] not found.'
                )
            screen_uniq_id: str = request.path_params[cls.SCREEN_UNIQ_ID_PARAM]
            try:
                request.state[cls.REQUEST_SCREEN_ATTR] = cls.get_event(
                    request
                ).screens_by_uniq_id[screen_uniq_id]
            except KeyError:
                raise NotFoundException(f'Screen [{screen_uniq_id}] not found.')
        return request.state[cls.REQUEST_SCREEN_ATTR]

    REQUEST_ROTATOR_ATTR: str = 'sharly_chess_rotator'
    ROTATOR_ID_PARAM: str = 'rotator_id'
    REQUEST_ROTATOR_SCREEN_INDEX_ATTR: str = 'sharly_chess_rotator_screen_index'
    ROTATOR_SCREEN_INDEX_PARAM: str = 'rotator_screen_index'

    @classmethod
    def get_rotator(
        cls,
        request: HTMXRequest,
    ) -> tuple[Rotator, int, Screen]:
        """Returns a tuple made of the rotator, the rotator screen index and the
        screen of the request (stored in the state of the request)."""
        if cls.REQUEST_ROTATOR_ATTR not in request.state:
            if cls.ROTATOR_ID_PARAM not in request.path_params:
                raise ClientException(
                    f'Path parameter [{cls.ROTATOR_ID_PARAM}] not found.'
                )
            rotator_id: int = request.path_params[cls.ROTATOR_ID_PARAM]
            try:
                rotator: Rotator = cls.get_event(request).rotators_by_id[rotator_id]
            except KeyError:
                raise NotFoundException(f'Rotator [{rotator_id}] not found.')
            rotator_screen_index: int = 0
            if cls.ROTATOR_SCREEN_INDEX_PARAM in request.path_params:
                rotator_screen_index = request.path_params[
                    cls.ROTATOR_SCREEN_INDEX_PARAM
                ] % len(rotator.rotating_screens)
            screen: Screen = rotator.rotating_screens[rotator_screen_index]
            request.state[cls.REQUEST_ROTATOR_ATTR] = rotator
            request.state[cls.REQUEST_ROTATOR_SCREEN_INDEX_ATTR] = rotator_screen_index
            request.state[cls.REQUEST_SCREEN_ATTR] = screen
        return (
            request.state[cls.REQUEST_ROTATOR_ATTR],
            request.state[cls.REQUEST_ROTATOR_SCREEN_INDEX_ATTR],
            request.state[cls.REQUEST_SCREEN_ATTR],
        )

    REQUEST_DISPLAY_CONTROLLER_ATTR: str = 'sharly_chess_display_controller'
    DISPLAY_CONTROLLER_ID_PARAM: str = 'display_controller_id'

    @classmethod
    def get_display_controller(
        cls,
        request: HTMXRequest,
    ) -> tuple[DisplayController, int, Screen]:
        """Returns a tuple made of the display controller, the rotator screen index and the
        screen of the request (stored in the state of the request)."""
        if cls.REQUEST_DISPLAY_CONTROLLER_ATTR not in request.state:
            if cls.DISPLAY_CONTROLLER_ID_PARAM not in request.path_params:
                raise ClientException(
                    f'Path parameter [{cls.DISPLAY_CONTROLLER_ID_PARAM}] not found.'
                )
            display_controller_id: int = request.path_params[
                cls.DISPLAY_CONTROLLER_ID_PARAM
            ]
            try:
                display_controller: DisplayController = cls.get_event(
                    request
                ).display_controllers_by_id[display_controller_id]
            except KeyError:
                raise NotFoundException(
                    f'Display controller [{display_controller_id}] not found.'
                )
            rotator_screen_index: int = 0
            if display_controller.rotator:
                if cls.ROTATOR_SCREEN_INDEX_PARAM in request.path_params:
                    rotator_screen_index = request.path_params[
                        cls.ROTATOR_SCREEN_INDEX_PARAM
                    ] % len(display_controller.rotator.rotating_screens)
                else:
                    rotator_screen_index = 0
                screen: Screen = display_controller.rotator.rotating_screens[
                    rotator_screen_index
                ]
            else:
                screen: Screen = display_controller.screen
            request.state[cls.REQUEST_DISPLAY_CONTROLLER_ATTR] = display_controller
            request.state[cls.REQUEST_ROTATOR_SCREEN_INDEX_ATTR] = rotator_screen_index
            request.state[cls.REQUEST_SCREEN_ATTR] = screen
        return (
            request.state[cls.REQUEST_DISPLAY_CONTROLLER_ATTR],
            request.state[cls.REQUEST_ROTATOR_SCREEN_INDEX_ATTR],
            request.state[cls.REQUEST_SCREEN_ATTR],
        )

    REQUEST_TOURNAMENT_ATTR: str = 'sharly_chess_tournament'
    TOURNAMENT_ID_PARAM: str = 'tournament_id'

    @classmethod
    def get_tournament(
        cls,
        request: HTMXRequest,
    ) -> Tournament:
        """Returns the tournament of the request, required (stored in the state of the request)."""
        if cls.REQUEST_TOURNAMENT_ATTR not in request.state:
            if cls.TOURNAMENT_ID_PARAM not in request.path_params:
                raise ClientException(
                    f'Path parameter [{cls.TOURNAMENT_ID_PARAM}] not found.'
                )
            tournament_id: int = request.path_params[cls.TOURNAMENT_ID_PARAM]
            try:
                request.state[cls.REQUEST_TOURNAMENT_ATTR] = cls.get_event(
                    request
                ).tournaments_by_id[tournament_id]
            except KeyError:
                raise NotFoundException(f'Tournament [{tournament_id}] not found.')
        return request.state[cls.REQUEST_TOURNAMENT_ATTR]

    REQUEST_BOARD_ATTR: str = 'sharly_chess_board'
    BOARD_ID_PARAM: str = 'board_id'

    @classmethod
    def get_board(
        cls,
        request: HTMXRequest,
    ) -> Board:
        """Returns the board of the request (stored in the state of the request)."""
        if cls.REQUEST_BOARD_ATTR not in request.state:
            tournament: Tournament = cls.get_tournament(request)
            if cls.BOARD_ID_PARAM not in request.path_params:
                raise ClientException(
                    f'Path parameter [{cls.BOARD_ID_PARAM}] not found.'
                )
            board_id: int = request.path_params[cls.BOARD_ID_PARAM]
            try:
                request.state[cls.REQUEST_BOARD_ATTR] = tournament.boards[board_id - 1]
            except KeyError:
                raise NotFoundException(f'Board [{board_id}] not found.')
        return request.state[cls.REQUEST_BOARD_ATTR]

    REQUEST_ROUND_ATTR: str = 'sharly_chess_round'
    ROUND_PARAM: str = 'round'
    REQUEST_RESULT_ATTR: str = 'sharly_chess_result'
    RESULT_PARAM: str = 'result'

    @classmethod
    def get_round_board_result(
        cls,
        request: HTMXRequest,
    ) -> tuple[int, Board, Result]:
        """Returns the round, board and (optional) result of the request (stored in the state of the request)."""
        if cls.REQUEST_ROUND_ATTR not in request.state:
            tournament: Tournament = cls.get_tournament(request)
            if cls.ROUND_PARAM not in request.path_params:
                raise ClientException(f'Path parameter [{cls.ROUND_PARAM}] not found.')
            request.state[cls.REQUEST_ROUND_ATTR] = request.path_params[cls.ROUND_PARAM]
            if request.state[cls.REQUEST_ROUND_ATTR] not in range(
                1, tournament.rounds + 1
            ):
                raise ClientException(
                    f'Invalid round number [{request.state[cls.REQUEST_ROUND_ATTR]}].'
                )
            try:
                request.state[cls.REQUEST_RESULT_ATTR] = Result(
                    request.path_params[cls.RESULT_PARAM]
                )
            except KeyError:
                request.state[cls.REQUEST_RESULT_ATTR] = Result.NO_RESULT
        return (
            request.state[cls.REQUEST_ROUND_ATTR],
            cls.get_board(request),
            request.state[cls.REQUEST_RESULT_ATTR],
        )

    REQUEST_PLAYER_ATTR: str = 'sharly_chess_player'
    PLAYER_ID_PARAM: str = 'player_id'

    @classmethod
    def get_player(
        cls,
        request: HTMXRequest,
    ) -> Player:
        """Returns the player of the request, required (stored in the state of the request)."""
        if cls.REQUEST_PLAYER_ATTR not in request.state:
            if cls.PLAYER_ID_PARAM not in request.path_params:
                raise ClientException(
                    f'Path parameter [{cls.PLAYER_ID_PARAM}] not found.'
                )
            player_id: int = request.path_params[cls.PLAYER_ID_PARAM]
            try:
                request.state[cls.REQUEST_PLAYER_ATTR] = cls.get_tournament(
                    request
                ).players_by_id[player_id]
            except KeyError:
                raise NotFoundException(f'Player [{player_id}] not found.')
        return request.state[cls.REQUEST_PLAYER_ATTR]
