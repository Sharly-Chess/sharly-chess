from litestar.exceptions import (
    PermissionDeniedException,
    NotFoundException,
    ClientException,
)
from litestar.handlers import BaseRouteHandler
from litestar_htmx import HTMXRequest

from common.exception import SharlyChessException
from data.auth.client import Client
from data.event import Event
from data.loader import EventLoader
from data.screen import Screen


class Guard:
    REQUEST_EVENT_ATTR: str = 'sharly_chess_event'
    EVENT_UNIQ_ID_PARAM: str = 'event_uniq_id'

    @classmethod
    def _get_event(cls, request: HTMXRequest) -> Event:
        """Returns the event of the request (stored in the state of the request)."""
        if cls.REQUEST_EVENT_ATTR not in request.state:
            try:
                event_uniq_id: str = request.path_params[cls.EVENT_UNIQ_ID_PARAM]
            except KeyError:
                raise ClientException
            try:
                request.state[cls.REQUEST_EVENT_ATTR] = EventLoader.get(
                    request
                ).load_event(event_uniq_id)
            except SharlyChessException as sce:
                raise NotFoundException from sce
        return request.state[cls.REQUEST_EVENT_ATTR]

    REQUEST_CLIENT_ATTR: str = 'sharly_chess_client'

    @classmethod
    def _get_client(cls, request: HTMXRequest) -> Client:
        """Returns the client of the request (stored in the state of the request)."""
        if cls.REQUEST_CLIENT_ATTR not in request.state:
            request.state[cls.REQUEST_CLIENT_ATTR] = Client(
                request, cls._get_event(request)
            )
        return request.state[cls.REQUEST_CLIENT_ATTR]

    REQUEST_SCREEN_ATTR: str = 'sharly_chess_screen'
    SCREEN_UNIQ_ID_PARAM: str = 'screen_uniq_id'

    @classmethod
    def _get_screen(cls, request: HTMXRequest) -> Screen:
        """Returns the screen of the request (stored in the state of the request)."""
        if cls.REQUEST_SCREEN_ATTR not in request.state:
            try:
                screen_uniq_id: str = request.path_params[cls.SCREEN_UNIQ_ID_PARAM]
            except KeyError:
                raise ClientException
            try:
                request.state[cls.REQUEST_SCREEN_ATTR] = cls._get_event(
                    request
                ).screens_by_uniq_id[screen_uniq_id]
            except KeyError:
                raise NotFoundException(f'Screen [{screen_uniq_id} not found')
        return request.state[cls.REQUEST_SCREEN_ATTR]

    @classmethod
    def screen_is_visible(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if the screen of the request is not visible."""
        client: Client = cls._get_client(request)
        screen: Screen = cls._get_screen(request)
        if screen.public:
            if not client.can_view_public_screens:
                raise PermissionDeniedException()
        else:
            if not client.can_view_private_screens:
                raise PermissionDeniedException()
