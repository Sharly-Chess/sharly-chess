from logging import Logger

from litestar import get
from litestar.config.response_cache import CACHE_FOREVER
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate
from litestar.response import Redirect, Template

from common.logger import get_logger
from web.controllers.base_controller import BaseController, WebContext
from web.messages import Message

logger: Logger = get_logger()


class IndexController(BaseController):
    @get(
        path='/',
        name='index',
        cache=1,
    )
    async def index(
        self,
        request: HTMXRequest,
        locale: str | None,
    ) -> Template:
        self.set_locale(request, locale)
        web_context: WebContext = WebContext(request)
        return HTMXTemplate(
            template_name='index.html',
            context=web_context.template_context
            | {
                'messages': Message.messages(request),
            },
        )
        
    @get(
        path='/empty-modal',
        name='empty-modal',
        cache=1,
    )
    async def empty_modal(
        self,
    ) -> Template:
        return HTMXTemplate(
            template_name='common/empty_modal.html',
            re_target='#modal-wrapper',
            push_url=False
        )   

    @get(
        path='/favicon.ico',
        name='favicon',
        cache=CACHE_FOREVER,
    )
    async def favicon(
        self,
        request: HTMXRequest,
    ) -> Redirect:
        return Redirect(
            request.app.route_reverse('static', file_path='/images/papi-web.ico')
        )
