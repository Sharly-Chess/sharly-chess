from litestar import get
from litestar.config.response_cache import CACHE_FOREVER
from litestar.exceptions import HTTPException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Redirect, Template

from web.controllers.base_controller import BaseController, WebContext
from web.messages import Message


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
    ) -> Template | Redirect:
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
        path='/wait',
        name='wait',
    )
    async def wait(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context: WebContext = WebContext(request)
        return HTMXTemplate(
            template_name='wait.html',
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
            request.app.route_reverse('static', file_path='/images/sharly-chess.ico')
        )

    @get(
        path='/404',
        name='404',
        cache=1,
    )
    async def handle_404(self, request: HTMXRequest) -> HTMXTemplate:
        web_context: WebContext = WebContext(request)

        return HTMXTemplate(
            template_name='exceptions/404.html',
            context=web_context.template_context,
        )

    @staticmethod
    def handle_404_exception(request: HTMXRequest, _exc: HTTPException) -> Redirect:
        return Redirect(path=request.app.route_reverse('404'))

    @get(
        path='/500',
        name='500',
        cache=1,
    )
    async def handle_500(self, request: HTMXRequest) -> HTMXTemplate:
        web_context: WebContext = WebContext(request)

        return HTMXTemplate(
            template_name='exceptions/500.html',
            context=web_context.template_context,
        )

    @staticmethod
    def handle_500_exception(request: HTMXRequest, _exc: HTTPException) -> Redirect:
        return Redirect(path=request.app.route_reverse('500'))
