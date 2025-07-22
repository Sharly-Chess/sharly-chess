from typing import Any

from litestar.plugins.htmx import HTMXRequest

from common.sharly_chess_config import SharlyChessConfig
from web.controllers.base_controller import BaseController, WebContext


class UserWebContext(WebContext):
    """
    The basic user web context, where parameter user_tab is passed to the template engine to propagate the context.
    """

    def __init__(
        self,
        request: HTMXRequest,
        user_tab: str | None,
    ):
        super().__init__(request, data=None)
        self.user_tab: str | None = user_tab
        if self.error:
            return
        self.check_user_tab()

    def check_user_tab(self):
        if self.user_tab not in [
            None,
            'passed_events',
            'current_events',
            'coming_events',
        ]:
            self._redirect_error(
                f'Invalid value [{self.user_tab}] for parameter [user_tab]'
            )

    @property
    def background_color(self) -> str:
        return SharlyChessConfig.user_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'user_tab': self.user_tab,
        }


class BaseUserController(BaseController):
    """An abstract class inherited by all the user controllers."""
