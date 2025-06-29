from typing import Annotated, Any

from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common.exception import SharlyChessException
from common.sharly_chess_config import SharlyChessConfig
from data.auth.client import Client
from data.event import Event
from data.loader import EventLoader
from web.controllers.user.base_user_controller import UserWebContext


class EventUserWebContext(UserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        user_event_tab: str | None,
    ):
        super().__init__(request, data=data, user_tab=None)
        self.user_event: Event | None = None
        self.user_event_tab: str | None = user_event_tab
        if self.error:
            return
        if not event_uniq_id:
            self._redirect_error('Event not set.')
            return
        try:
            self.user_event = EventLoader.get(request=self.request).load_event(
                event_uniq_id
            )
            if self.user_event.public or self.admin_auth:
                self.user_event_tab = user_event_tab
                return
            self._redirect_error(f'Access denied for event [{event_uniq_id}].')
        except SharlyChessException as pwe:
            self._redirect_error(f'Event [{event_uniq_id}] not found: {pwe}.')

    @property
    def client(self) -> Client:
        """Returns the client (account and computer) of the request."""
        return Client(self.request, self.user_event)

    def check_user_tab(self):
        pass

    @property
    def background_image(self) -> str | None:
        return None

    @property
    def background_color(self) -> str:
        return SharlyChessConfig.user_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'user_event_tab': self.user_event_tab,
            'user_event': self.user_event,
        }
