from functools import cached_property
from typing import Any

from litestar.plugins.htmx import HTMXRequest

from common.sharly_chess_config import SharlyChessConfig
from data.auth.client import Client
from data.auth.client_tracker import ClientTracker
from data.event import Event
from web.controllers.user.base_user_controller import UserWebContext, BaseUserController
from web.guards import Guard
from web.utils import RequestUtils


class EventUserWebContext(UserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        user_event_tab: str | None,
    ):
        super().__init__(request, user_tab=None)
        self.user_event: Event = RequestUtils.get_event(request)
        self.user_event_tab: str | None = user_event_tab
        if self.error:
            return
        # tracks the visit of the client
        ClientTracker().track_client(
            self.client.host,
            self.client.event.uniq_id if self.client.event else None,
            self.client.account.username if self.client.account else None,
        )

    @cached_property
    def client(self) -> Client:
        """Returns the client (account and device) of the request."""
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


class EventUserController(BaseUserController):
    """An abstract class inherited by the user controllers depending on an event."""

    event_guards = [
        Guard.event_is_visible,
    ]
