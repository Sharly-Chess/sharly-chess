import asyncio
import json
from typing import AsyncGenerator

from litestar import Response, get, route, HttpMethod, status_codes
from litestar.config.response_cache import CACHE_FOREVER
from litestar.exceptions import HTTPException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Redirect, Template
from litestar.channels import ChannelsPlugin
from litestar.response import ServerSentEventMessage, ServerSentEvent

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from web.controllers.base_controller import BaseController, WebContext
from web.messages import Message


class IndexController(BaseController):
    ALL_HTTP_METHODS: list[HttpMethod] = [
        HttpMethod.GET,
        HttpMethod.POST,
        HttpMethod.PATCH,
        HttpMethod.PUT,
        HttpMethod.HEAD,
        HttpMethod.OPTIONS,
    ]

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

        if not web_context.admin_auth:
            return Redirect(request.app.route_reverse('user'))

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
            request.app.route_reverse(
                'static',
                file_path='/images/sharly-chess.ico',
                version=SharlyChessConfig.version,
            )
        )

    @staticmethod
    def _error_template(
        request: HTMXRequest,
        status_code: int,
    ):
        reload_message: str | None = None
        title: str
        error_message: str
        if request.htmx:
            reload_message = _('Reload the page')
        match status_code:
            case status_codes.HTTP_401_UNAUTHORIZED:
                title = _('401 - Authentication failed')
                error_message = _('Sorry, authorization failed.')
                if request.htmx:
                    reload_message = _('Retry')
            case status_codes.HTTP_403_FORBIDDEN:
                title = _('403 - Access Forbidden')
                error_message = _('Sorry, you are not allowed to access this page.')
                if request.htmx:
                    reload_message = _('Retry')
            case status_codes.HTTP_404_NOT_FOUND:
                title = _('404 - Page Not Found')
                error_message = _('Sorry, the page you are looking for does not exist.')
                reload_message = None
            case status_codes.HTTP_500_INTERNAL_SERVER_ERROR:
                title = _('500 - Internal Server Error')
                error_message = _('Sorry, an unexpected error has occurred.')
            case _:
                title = _('{status_code} - Unknown error').format(
                    status_code=status_code
                )
                error_message = _('An unexpected error occurred.')
        return HTMXTemplate(
            template_name='/error.html',
            context=WebContext(request).template_context
            | {
                'reload_message': reload_message,
                'error_title': title,
                'error_message': error_message,
            },
            re_target='body',
        )

    @classmethod
    def handle_exception(
        cls, request: HTMXRequest, exception: HTTPException
    ) -> Redirect | HTMXTemplate:
        status_code = getattr(exception, 'status_code', 500)
        if request.htmx:
            return cls._error_template(request, status_code)
        return Redirect(
            path=request.app.route_reverse('http-error', status_code=status_code)
        )

    @route(
        http_method=ALL_HTTP_METHODS,
        path='/error/{status_code:int}',
        name='http-error',
        cache=1,
    )
    async def handle_http_error(
        self, request: HTMXRequest, status_code: int
    ) -> HTMXTemplate:
        return self._error_template(request, status_code)

    @get('/sse')
    async def sse_handler(self, channels: ChannelsPlugin) -> ServerSentEvent:
        async def generator() -> AsyncGenerator[ServerSentEventMessage, None]:
            try:
                async with channels.start_subscription(['sse']) as subscriber:
                    async for raw_event in subscriber.iter_events():
                        # Parse from string if needed
                        if isinstance(raw_event, (bytes, str)):
                            event = json.loads(raw_event)
                        else:
                            event = raw_event

                        yield ServerSentEventMessage(
                            event=event.get('event', 'message'),
                            data=event.get('data', ''),
                        )
            except asyncio.CancelledError:
                return

        return ServerSentEvent(generator())

    @get('/.well-known/appspecific/com.chrome.devtools.json')
    async def chrome_devtools_placeholder(self) -> Response:
        return Response(content='{}', media_type='application/json')
