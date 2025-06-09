import asyncio
import json
from typing import AsyncGenerator
from litestar import Response, get, route, HttpMethod
from litestar.config.response_cache import CACHE_FOREVER
from litestar.exceptions import HTTPException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Redirect, Template
from litestar.channels import ChannelsPlugin
from litestar.response import ServerSentEventMessage, ServerSentEvent

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

    @route(
        http_method=ALL_HTTP_METHODS,
        path='/403',
        name='403',
        cache=1,
    )
    async def handle_403(self, request: HTMXRequest) -> HTMXTemplate:
        web_context: WebContext = WebContext(request)

        return HTMXTemplate(
            template_name='errors/403.html',
            context=web_context.template_context,
            re_target='body',
        )

    @staticmethod
    def handle_403_exception(request: HTMXRequest, _exc: HTTPException) -> Redirect:
        return Redirect(path=request.app.route_reverse('403'))

    @route(
        http_method=ALL_HTTP_METHODS,
        path='/404',
        name='404',
        cache=1,
    )
    async def handle_404(self, request: HTMXRequest) -> HTMXTemplate:
        web_context: WebContext = WebContext(request)

        return HTMXTemplate(
            template_name='errors/404.html',
            context=web_context.template_context,
            re_target='body',
        )

    @staticmethod
    def handle_404_exception(request: HTMXRequest, _exc: HTTPException) -> Redirect:
        return Redirect(path=request.app.route_reverse('404'))

    @route(
        http_method=ALL_HTTP_METHODS,
        path='/500',
        name='500',
        cache=1,
    )
    async def handle_500(self, request: HTMXRequest) -> HTMXTemplate:
        web_context: WebContext = WebContext(request)

        return HTMXTemplate(
            template_name='errors/500.html',
            context=web_context.template_context,
            re_target='body',
        )

    @staticmethod
    def handle_500_exception(request: HTMXRequest, _exc: HTTPException) -> Redirect:
        return Redirect(path=request.app.route_reverse('500'))

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
