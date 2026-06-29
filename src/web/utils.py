import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from data.event_load_spec import EventLoadSpec

from anyio import run
from litestar.exceptions import (
    NotFoundException,
    ValidationException,
    ClientException,
)
from litestar_htmx import HTMXRequest

from common.exception import SharlyChessException
from common.logger import get_logger
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
from plugins.manager import plugin_manager
from utils.enum import Result

logger = get_logger()


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

    @staticmethod
    def _handler_event_load_spec(
        request: HTMXRequest,
    ) -> 'EventLoadSpec | None':
        """Read the `@needs_event(...)` spec attached to the route handler,
        if any, and resolve it against the current request's path/query
        params. Returns None when the handler isn't decorated."""
        from data.event_load_spec import get_handler_spec

        handler = request.scope.get('route_handler')
        if handler is None:
            return None
        fn = getattr(handler, 'fn', None) or handler
        params: dict[str, Any] = {}
        try:
            params.update(dict(request.path_params))
        except Exception:
            pass
        try:
            params.update(dict(request.query_params))
        except Exception:
            pass
        return get_handler_spec(fn, request, params)

    @classmethod
    def get_event(cls, request: HTMXRequest, reload: bool = False) -> Event:
        if cls.REQUEST_EVENT_ATTR in request.state and not reload:
            return request.state[cls.REQUEST_EVENT_ATTR]
        event_uniq_id = cls._get_request_param(request, cls.EVENT_UNIQ_ID_PARAM)
        # If the route handler declared a `@needs_event(...)` spec, use it
        # to load only the requested subset. Default = full load.
        spec = cls._handler_event_load_spec(request)
        try:
            event = EventLoader.get(request).load_event(event_uniq_id, spec=spec)
        except SharlyChessException as sce:
            raise NotFoundException(f'Event [{event_uniq_id}] not found.') from sce
        for plugin_id in event.stored_event.enabled_plugins:
            if not plugin_manager.plugins_by_id[plugin_id].is_enabled:
                raise ClientException(
                    f'Event [{event_uniq_id}] - '
                    f'Required plugin [{plugin_id}] not enabled.'
                )
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
    def get_client(cls, request: HTMXRequest, reload: bool = False) -> Client:
        if reload or cls.REQUEST_CLIENT_ATTR not in request.state:
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

    @classmethod
    def get_optional_screen(cls, request: HTMXRequest) -> Screen | None:
        try:
            return cls.get_screen(request)
        except ValidationException:
            return None

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

    @classmethod
    def get_optional_display_controller(
        cls, request: HTMXRequest
    ) -> DisplayController | None:
        try:
            return cls.get_display_controller(request)
        except ValidationException:
            return None

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
    subtitle: str | None = None


class PKCEUtils:
    @staticmethod
    def generate_code_verifier() -> str:
        return (
            base64.urlsafe_b64encode(secrets.token_bytes(32))
            .rstrip(b'=')
            .decode('ascii')
        )

    @staticmethod
    def generate_code_challenge(verifier: str) -> str:
        sha256 = hashlib.sha256(verifier.encode('ascii')).digest()
        return base64.urlsafe_b64encode(sha256).rstrip(b'=').decode('ascii')

    @staticmethod
    def generate_state() -> str:
        return secrets.token_hex(16)
