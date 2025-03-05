from logging import Logger
from typing import Annotated, Any

from litestar.contrib.htmx.request import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from web.controllers.index_controller import BaseController, WebContext

logger: Logger = get_logger()

class UserWebContext(WebContext):
    """
    The basic user web context, where parameter user_tab is passed to the template engine to propagate the context.
    """

    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        user_tab: str | None,
    ):
        super().__init__(request, data=data)
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
        return PapiWebConfig.user_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'user_tab': self.user_tab,
        }
        
class BaseUserController(BaseController):
    """An abstract class inherited by all the user controllers."""

