import urllib
from abc import ABC, abstractmethod
from typing import cast

from litestar.connection.base import ASGIConnection
from litestar.exceptions import (
    PermissionDeniedException,
    ClientException,
    NotFoundException,
)
from litestar.handlers import BaseRouteHandler
from litestar_htmx import HTMXRequest

from data.access_levels.actions import AuthAction
from data.access_levels.client import Client
from data.display_controller import DisplayController
from data.rotator import Rotator
from data.screen import Screen
from data.tournament import Tournament
from utils.enum import Result
from web.utils import RequestUtils


class BaseGuard(ABC):
    """Base class of all the endpoint or controller guards.
    Usage:
        class Controller:
            guards = [ControllerGuard()]

        @get(
            path='/endpoint/example',
            name='endpoint-example',
            guards=[EndpointGuard()],
        )
        async def endpoint_example():...
    """

    def __call__(self, connection: ASGIConnection, _: BaseRouteHandler):
        request = cast(HTMXRequest, connection)
        client = RequestUtils.get_client(request)
        self.authorize_client(client, request)

    @abstractmethod
    def authorize_client(self, client: Client, request: HTMXRequest):
        """Validate that the client is authorized by the guard.
        Should fetch the necessary request data using RequestUtils,
        then raises a PermissionDeniedException if the client is not authorized.
        """

    @staticmethod
    def _authorize_action(action: AuthAction, client: Client):
        if action not in client.allowed_actions:
            raise PermissionDeniedException(
                f'Client [{client.account.full_name}] is not allowed '
                f'to perform the action [{action.localized_name("en")}].'
            )

    @staticmethod
    def _authorize_tournament_action(
        action: AuthAction,
        client: Client,
        request: HTMXRequest,
        search_form: bool = False,
        tournament: Tournament | None = None,
    ):
        if not tournament:
            tournament = RequestUtils.get_tournament(request, search_form)
        if not client.action_allowed_for_tournament(action, tournament.id):
            raise PermissionDeniedException(
                f'Client [{client.account.full_name}] is not allowed '
                f'to perform the action [{action.localized_name("en")}] '
                f'on tournament [{tournament.name}].'
            )


class ActionGuard(BaseGuard):
    """Guard validating if an action is allowed for the client."""

    def __init__(self, action: AuthAction):
        self.action = action

    def authorize_client(self, client: Client, request: HTMXRequest):
        self._authorize_action(self.action, client)


class TournamentActionGuard(ActionGuard):
    """Guard validating if an action is allowed for the client on a tournament.
    Falls back to an ActionGuard if no tournament is provided.
    optional: event_uniq_id, tournament_id."""

    def __init__(self, action: AuthAction, search_form: bool = False):
        super().__init__(action)
        self.search_form = search_form

    def authorize_client(self, client: Client, request: HTMXRequest):
        if RequestUtils.get_optional_tournament(request, self.search_form):
            self._authorize_tournament_action(self.action, client, request)
        else:
            self._authorize_action(self.action, client)


class PlayerTournamentActionGuard(ActionGuard):
    """Guard validating if an action is allowed for the client on
    one of the tournaments of the player.
    Required: event_uniq_id, player_id."""

    def authorize_client(self, client: Client, request: HTMXRequest):
        player = RequestUtils.get_player(request)
        if not client.action_allowed_for_player(self.action, player):
            raise PermissionDeniedException(
                f'Client [{client.account.full_name}] is not allowed '
                f'to perform the action [{self.action.localized_name("en")}] '
                f'on player [{player.full_name}].'
            )


class EventGuard(BaseGuard):
    """Guard validating if the client can access an event.
    requires: event_uniq_id"""

    def authorize_client(self, client: Client, request: HTMXRequest):
        event = RequestUtils.get_event(request)
        if not event.public:
            self._authorize_action(AuthAction.VIEW_PRIVATE_EVENTS, client)
        if event.passed:
            self._authorize_action(AuthAction.VIEW_PASSED_EVENTS, client)


class SetResultGuard(BaseGuard):
    """Guard validating if a client can set a result on a board.
    requires: event_uniq_id, tournament_id, board_id, result."""

    def authorize_client(self, client: Client, request: HTMXRequest):
        board = RequestUtils.get_board(request)
        result = RequestUtils.get_result(request)
        self._authorize_tournament_action(AuthAction.ENTER_RESULTS, client, request)
        if not board.no_result:
            self._authorize_tournament_action(
                AuthAction.UPDATE_RESULTS, client, request
            )
        if result.is_special_result:
            self._authorize_tournament_action(
                AuthAction.SET_SPECIAL_RESULTS, client, request
            )


class SetByeGuard(BaseGuard):
    """Guard validating if a client can set a bye for a player.
    requires: event_uniq_id, result."""

    def authorize_client(self, client: Client, request: HTMXRequest):
        result = RequestUtils.get_result(request)
        if result == Result.HALF_POINT_BYE:
            action = AuthAction.SET_HPB
        elif result == Result.FULL_POINT_BYE:
            action = AuthAction.SET_FPB
        elif result in [Result.NO_RESULT, Result.ZERO_POINT_BYE]:
            action = AuthAction.SET_ZPB
        else:
            raise ClientException(f'Result [{result.value}] is not a bye')
        self._authorize_action(action, client)


class ViewScreenEntityGuard[T](BaseGuard, ABC):
    @staticmethod
    @abstractmethod
    def get_entity(request: HTMXRequest) -> T | None:
        """Get the optional entity from the request."""

    @staticmethod
    def is_entity_public(entity: T) -> bool:
        return entity.public

    def authorize_client(self, client: Client, request: HTMXRequest):
        entity = self.get_entity(request)
        if not entity:
            return
        action = (
            AuthAction.VIEW_PUBLIC_SCREENS
            if self.is_entity_public(entity)
            else AuthAction.VIEW_PRIVATE_SCREENS
        )
        self._authorize_action(action, client)


class ViewScreenGuard(ViewScreenEntityGuard[Screen]):
    """Guard validating if a client can view a screen.
    requires: event_uniq_id
    optional: screen_uniq_id."""

    @staticmethod
    def get_entity(request: HTMXRequest) -> Screen | None:
        return RequestUtils.get_optional_screen(request)


class ViewRotatorGuard(ViewScreenEntityGuard[Rotator]):
    """Guard validating if a client can view a rotator.
    requires: event_uniq_id
    optional: rotator_id."""

    @staticmethod
    def get_entity(request: HTMXRequest) -> Rotator | None:
        return RequestUtils.get_optional_rotator(request)


class ViewDisplayControllerGuard(ViewScreenEntityGuard[DisplayController]):
    """Guard validating if a client can view a display controller.
    requires: event_uniq_id
    optional: display_controller_id."""

    @staticmethod
    def get_entity(request: HTMXRequest) -> DisplayController | None:
        return RequestUtils.get_optional_display_controller(request)


class ManageScreenEntityGuard(BaseGuard):
    """Guard validating the management of a screen entity.
    optional: {path_param}."""

    def __init__(self, path_param: str):
        self.path_param = path_param

    def authorize_client(self, client: Client, request: HTMXRequest):
        if self.path_param in request.path_params:
            self._authorize_action(AuthAction.MANAGE_SCREENS, client)


class ManageAccountGuard(BaseGuard):
    """Guard validating if an account can be managed by the client.
    optional: account_id, access_level"""

    def authorize_client(self, client: Client, request: HTMXRequest):
        account = RequestUtils.get_optional_account(request)
        if not account:
            return
        if not client.can_manage_account(account.id):
            raise PermissionDeniedException(
                f'Client [{client.account.full_name}] can not '
                f'manage account [{account.full_name}].'
            )
        access_level = RequestUtils.get_optional_access_level(request)
        if access_level and access_level not in client.manageable_access_levels:
            raise PermissionDeniedException(
                f'Client [{client.account.full_name}] can not '
                f'manage access level [{access_level.id}].'
            )


class PrintGuard(BaseGuard):
    """Guard validating if the client is allowed to generate a print view."""

    def authorize_client(self, client: Client, request: HTMXRequest):
        options = request.query_params.get('options', None)
        if not options:
            return
        tournament_ids: list[int] = []
        for option in urllib.parse.unquote(options).split('|'):
            key, raw_value = option.split('=')
            if key == 'tournament':
                tournament_ids.append(int(raw_value))
            if key == 'tournaments':
                for item in raw_value.split(';'):
                    tournament_ids.append(int(item))
        event = RequestUtils.get_event(request)
        for tournament_id in tournament_ids:
            if tournament_id not in event.tournaments_by_id:
                raise NotFoundException(f'Tournament [{tournament_id}] not found.')
            self._authorize_tournament_action(
                AuthAction.GENERATE_DOCUMENTS,
                client,
                request,
                tournament=event.tournaments_by_id[tournament_id],
            )
