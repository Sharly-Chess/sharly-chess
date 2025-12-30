from abc import ABC
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from anyio import run
from litestar.exceptions import (
    NotFoundException,
    ValidationException,
)
from litestar_htmx import HTMXRequest

from common.exception import SharlyChessException
from data.access_levels.access_levels import AccessLevel
from data.access_levels.client import Client
from data.access_levels.manager import AccessLevelManager
from data.account import Account
from data.board import Board
from data.display_controller import DisplayController
from data.event import Event
from data.loader import EventLoader
from data.player import TournamentPlayer, Player
from data.rotator import Rotator
from data.screen import Screen
from data.tournament import Tournament
from utils.enum import Result


class RequestUtils:
    """Class fetching objects from the requests path params
    and storing them into the request."""

    @staticmethod
    def _get_request_param(
        request: HTMXRequest, param: str, search_form: bool = False
    ) -> Any:
        if value := request.path_params.get(param, None):
            return value
        if value := request.query_params.get(param, None):
            if isinstance(value, str) and value.isdigit():
                return int(value)
            return value
        if search_form:
            form_data = run(lambda: request.form())
            if value := form_data.get(param, None):
                if isinstance(value, str) and value.isdigit():
                    return int(value)
                return value
        raise ValidationException(f'Parameter [{param}] not found.')

    REQUEST_EVENT_ATTR: str = 'sharly_chess_event'
    EVENT_UNIQ_ID_PARAM: str = 'event_uniq_id'

    @classmethod
    def get_event(cls, request: HTMXRequest, reload: bool = False) -> Event:
        if cls.REQUEST_EVENT_ATTR in request.state and not reload:
            return request.state[cls.REQUEST_EVENT_ATTR]
        event_uniq_id = cls._get_request_param(request, cls.EVENT_UNIQ_ID_PARAM)
        try:
            event = EventLoader.get(request).load_event(event_uniq_id)
        except SharlyChessException as sce:
            raise NotFoundException(f'Event [{event_uniq_id}] not found.') from sce
        request.state[cls.REQUEST_EVENT_ATTR] = event
        return event

    @classmethod
    def get_optional_event(
        cls, request: HTMXRequest, reload: bool = False
    ) -> Event | None:
        try:
            return cls.get_event(request, reload)
        except ValidationException:
            return None

    REQUEST_CLIENT_ATTR: str = 'sharly_chess_client'

    @classmethod
    def get_client(cls, request: HTMXRequest) -> Client:
        if cls.REQUEST_CLIENT_ATTR not in request.state:
            request.state[cls.REQUEST_CLIENT_ATTR] = Client(
                request, cls.get_optional_event(request)
            )
        return request.state[cls.REQUEST_CLIENT_ATTR]

    REQUEST_SCREEN_ATTR: str = 'sharly_chess_screen'
    SCREEN_UNIQ_ID_PARAM: str = 'screen_uniq_id'

    @classmethod
    def get_screen(cls, request: HTMXRequest) -> Screen:
        if cls.REQUEST_SCREEN_ATTR in request.state:
            return request.state[cls.REQUEST_SCREEN_ATTR]
        screen_uniq_id = cls._get_request_param(request, cls.SCREEN_UNIQ_ID_PARAM)
        try:
            screen = cls.get_event(request).screens_by_uniq_id[screen_uniq_id]
        except KeyError:
            raise NotFoundException(f'Screen [{screen_uniq_id}] not found.')
        request.state[cls.REQUEST_SCREEN_ATTR] = screen
        return screen

    REQUEST_ROTATOR_ATTR: str = 'sharly_chess_rotator'
    ROTATOR_ID_PARAM: str = 'rotator_id'

    @classmethod
    def get_rotator(cls, request: HTMXRequest) -> Rotator:
        if cls.REQUEST_ROTATOR_ATTR in request.state:
            return request.state[cls.REQUEST_ROTATOR_ATTR]
        rotator_id = cls._get_request_param(request, cls.ROTATOR_ID_PARAM)
        try:
            rotator = cls.get_event(request).rotators_by_id[rotator_id]
        except KeyError:
            raise NotFoundException(f'Rotator [{rotator_id}] not found.')
        request.state[cls.REQUEST_ROTATOR_ATTR] = rotator
        return rotator

    @classmethod
    def get_optional_rotator(cls, request: HTMXRequest) -> Rotator | None:
        try:
            return cls.get_rotator(request)
        except ValidationException:
            return None

    REQUEST_DISPLAY_CONTROLLER_ATTR: str = 'sharly_chess_display_controller'
    DISPLAY_CONTROLLER_ID_PARAM: str = 'display_controller_id'

    @classmethod
    def get_display_controller(cls, request: HTMXRequest) -> DisplayController:
        if cls.REQUEST_DISPLAY_CONTROLLER_ATTR in request.state:
            return request.state[cls.REQUEST_DISPLAY_CONTROLLER_ATTR]
        display_controller_id = cls._get_request_param(
            request, cls.DISPLAY_CONTROLLER_ID_PARAM
        )
        try:
            display_controller = cls.get_event(request).display_controllers_by_id[
                display_controller_id
            ]
        except KeyError:
            raise NotFoundException(
                f'Display controller [{display_controller_id}] not found.'
            )
        request.state[cls.REQUEST_DISPLAY_CONTROLLER_ATTR] = display_controller
        return display_controller

    REQUEST_TOURNAMENT_ATTR: str = 'sharly_chess_tournament'
    TOURNAMENT_ID_PARAM: str = 'tournament_id'

    @classmethod
    def get_tournament(
        cls, request: HTMXRequest, search_form: bool = False
    ) -> Tournament:
        if cls.REQUEST_TOURNAMENT_ATTR in request.state:
            return request.state[cls.REQUEST_TOURNAMENT_ATTR]
        tournament_id = cls._get_request_param(
            request, cls.TOURNAMENT_ID_PARAM, search_form
        )
        try:
            tournament = cls.get_event(request).tournaments_by_id[tournament_id]
        except KeyError:
            raise NotFoundException(f'Tournament [{tournament_id}] not found.')
        request.state[cls.REQUEST_TOURNAMENT_ATTR] = tournament
        return tournament

    @classmethod
    def get_optional_tournament(
        cls, request: HTMXRequest, search_form: bool = False
    ) -> Tournament | None:
        try:
            return cls.get_tournament(request, search_form)
        except ValidationException:
            return None

    REQUEST_BOARD_ATTR: str = 'sharly_chess_board'
    BOARD_INDEX_PARAM: str = 'board_id'
    ROUND_PARAM: str = 'round'

    @classmethod
    def get_board(cls, request: HTMXRequest) -> Board:
        # TODO (Molrn) use board IDs instead of board index in every request
        if cls.REQUEST_BOARD_ATTR in request.state:
            return request.state[cls.REQUEST_BOARD_ATTR]
        tournament: Tournament = cls.get_tournament(request)
        board_index = cls._get_request_param(request, cls.BOARD_INDEX_PARAM)
        round_ = request.path_params.get(cls.ROUND_PARAM, tournament.current_round)
        if not 0 <= round_ <= tournament.rounds:
            raise ValidationException(f'Invalid round number [{round_}].')
        board = next(
            (
                board_
                for board_ in tournament.get_round_boards(round_)
                if board_.id == board_index
            ),
            None,
        )
        if not board:
            raise NotFoundException(f'Board [{board_index}] not found.')
        request.state[cls.REQUEST_BOARD_ATTR] = board
        return board

    REQUEST_RESULT_ATTR: str = 'sharly_chess_result'
    RESULT_PARAM: str = 'result'

    @classmethod
    def get_result(
        cls,
        request: HTMXRequest,
    ) -> Result:
        if cls.REQUEST_RESULT_ATTR in request.state:
            return request.state[cls.REQUEST_RESULT_ATTR]
        result_value = request.path_params.get(cls.RESULT_PARAM, None)
        if result_value is not None:
            try:
                result = Result(result_value)
            except ValueError:
                raise NotFoundException(f'Unknown result [{result_value}].')
        else:
            result = Result.NO_RESULT
        request.state[cls.REQUEST_RESULT_ATTR] = result
        return result

    REQUEST_PLAYER_ATTR: str = 'sharly_chess_player'
    REQUEST_TOURNAMENT_PLAYER_ATTR: str = 'sharly_chess_tournament_player'
    PLAYER_ID_PARAM: str = 'player_id'

    @classmethod
    def get_player(cls, request: HTMXRequest) -> Player:
        if cls.REQUEST_PLAYER_ATTR in request.state:
            return request.state[cls.REQUEST_PLAYER_ATTR]
        player_id = cls._get_request_param(request, cls.PLAYER_ID_PARAM)
        try:
            request.state[cls.REQUEST_PLAYER_ATTR] = cls.get_event(
                request
            ).players_by_id[player_id]
        except KeyError:
            raise NotFoundException(f'Player [{player_id}] not found.')
        return request.state[cls.REQUEST_PLAYER_ATTR]

    @classmethod
    def get_tournament_player(cls, request: HTMXRequest) -> TournamentPlayer:
        if cls.REQUEST_PLAYER_ATTR in request.state:
            return request.state[cls.REQUEST_PLAYER_ATTR]
        player_id = cls._get_request_param(request, cls.PLAYER_ID_PARAM)
        tournament = cls.get_tournament(request)
        try:
            request.state[cls.REQUEST_PLAYER_ATTR] = (
                tournament.tournament_players_by_id[player_id]
            )
        except KeyError:
            raise NotFoundException(
                f'Player [{player_id}] not found in tournament [{tournament.name}].'
            )
        return request.state[cls.REQUEST_PLAYER_ATTR]

    REQUEST_ACCOUNT_ATTR: str = 'sharly_chess_account'
    ACCOUNT_ID_PARAM: str = 'account_id'

    @classmethod
    def get_account(cls, request: HTMXRequest) -> Account:
        if cls.REQUEST_ACCOUNT_ATTR in request.state:
            return request.state[cls.REQUEST_ACCOUNT_ATTR]
        account_id = cls._get_request_param(request, cls.ACCOUNT_ID_PARAM)
        try:
            account = cls.get_event(request).accounts_by_id[account_id]
        except KeyError:
            raise NotFoundException(f'Account [{account_id}] not found.')
        request.state[cls.REQUEST_ACCOUNT_ATTR] = account
        return account

    @classmethod
    def get_optional_account(cls, request: HTMXRequest) -> Account | None:
        try:
            return cls.get_account(request)
        except ValidationException:
            return None

    REQUEST_ACCESS_LEVEL_ATTR: str = 'sharly_chess_access_level'
    ACCESS_LEVEL_PARAM: str = 'access_level'

    @classmethod
    def get_access_level(cls, request: HTMXRequest) -> AccessLevel:
        if cls.REQUEST_ACCESS_LEVEL_ATTR in request.state:
            return request.state[cls.REQUEST_ACCESS_LEVEL_ATTR]
        access_level_id = cls._get_request_param(request, cls.ACCESS_LEVEL_PARAM)
        try:
            access_level = AccessLevelManager().get_object(access_level_id)
        except KeyError:
            raise NotFoundException(f'Unknown access level [{access_level_id}].')
        request.state[cls.REQUEST_ACCESS_LEVEL_ATTR] = access_level
        return access_level

    @classmethod
    def get_optional_access_level(cls, request: HTMXRequest) -> AccessLevel | None:
        try:
            return cls.get_access_level(request)
        except ValidationException:
            return None


@dataclass
class SelectOption:
    name: str
    tooltip: str | None = None
    disabled: bool = False
    classes: str = ''
    search: str | None = None


class Column[T](ABC):
    @property
    def grid_column_template(self) -> str:
        """The width definition of the content as used by grid-template-columns"""
        return 'max-content'

    @property
    def header_content(self) -> str:
        """The content of the header as a string.
        A template can be used for more complex headers."""
        raise NotImplementedError(
            'The header content needs to be implemented '
            'if a template for the header is not provided.'
        )

    @property
    def is_header_content_safe(self) -> bool:
        """Defines if the header content is safe to be displayed in Jinja.
        User-input strings should not be declared as safe.
        Useful to add light html formatting (ex: <b>last_name</b> first_name)"""
        return False

    @property
    def header_template(self) -> str | None:
        """The template to use for the header of the column.
        If None, the header content is used."""
        return None

    @property
    def header_classes(self) -> str:
        """CSS classes to use for the header."""
        return self.shared_classes

    def get_cell_content(self, object_: T) -> Any:
        """Get the content of a cell as a string from an object of the table.
        A template can be used for more complex cell contents."""
        raise NotImplementedError(
            'The cell content needs to be implemented '
            'if a template for the cell is not provided.'
        )

    @property
    def is_cell_content_safe(self) -> bool:
        """Defines if the cell content is safe to be displayed in Jinja.
        User-input strings should not be declared as safe.
        Useful to add light html formatting (ex: <b>last_name</b> first_name)"""
        return False

    @property
    def cell_template(self) -> str | None:
        """The template to use for the cells. If None, the cell content is used."""
        return None

    def get_cell_classes(self, object_: T) -> str:
        """CSS classes to use for the cells."""
        return self.shared_classes

    @property
    def shared_classes(self) -> str:
        """Classes shared between the cells and the header."""
        return ''


class ColumnUsage(Enum):
    SCREEN = auto()
    PRINT = auto()
