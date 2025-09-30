from abc import ABC, abstractmethod
from typing import cast

from litestar.connection.base import ASGIConnection
from litestar.exceptions import PermissionDeniedException
from litestar.handlers import BaseRouteHandler
from litestar_htmx import HTMXRequest

from data.access_levels.actions import AuthAction
from data.access_levels.client import Client
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
        action: AuthAction, client: Client, request: HTMXRequest
    ):
        tournament = RequestUtils.get_tournament(request)
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

    def authorize_client(self, client: Client, request: HTMXRequest):
        if RequestUtils.get_optional_tournament(request):
            self._authorize_tournament_action(self.action, client, request)
        else:
            self._authorize_action(self.action, client)


class EventGuard(BaseGuard):
    """Guard validating if the client can access an event.
    requires: event_uniq_id"""

    def authorize_client(self, client: Client, request: HTMXRequest):
        event = RequestUtils.get_event(request)
        if not event.public:
            self._authorize_action(AuthAction.VIEW_PRIVATE_EVENTS, client)
        if event.passed():
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


class ViewScreenEntityGuard(BaseGuard, ABC):
    """Base guard for validating viewing a private / public screen entity."""

    @staticmethod
    @abstractmethod
    def is_public(request: HTMXRequest) -> bool:
        """Get the visibility status of the entity."""

    def authorize_client(self, client: Client, request: HTMXRequest):
        if not self.is_public(request):
            self._authorize_action(AuthAction.VIEW_PRIVATE_SCREENS, client)
        else:
            self._authorize_action(AuthAction.VIEW_PUBLIC_SCREENS, client)


class ViewScreenGuard(ViewScreenEntityGuard):
    """Guard validating if a client can view a screen.
    requires: event_uniq_id, screen_uniq_id."""

    @staticmethod
    def is_public(request: HTMXRequest) -> bool:
        return RequestUtils.get_screen(request).public


class ViewRotatorGuard(ViewScreenEntityGuard):
    """Guard validating if a client can view a rotator.
    requires: event_uniq_id, rotator_id."""

    @staticmethod
    def is_public(request: HTMXRequest) -> bool:
        return RequestUtils.get_rotator(request).public


class ViewDisplayControllerGuard(ViewScreenEntityGuard):
    """Guard validating if a client can view a display controller.
    requires: event_uniq_id, display_controller_id."""

    @staticmethod
    def is_public(request: HTMXRequest) -> bool:
        return RequestUtils.get_display_controller(request).public


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
