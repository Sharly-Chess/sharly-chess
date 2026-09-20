import asyncio
import platform
import signal
import socket
import sys
from threading import Thread
from time import sleep
from types import FrameType
from typing import ClassVar, cast
from collections.abc import Callable
from webbrowser import open

import requests
import uvicorn
from litestar import Litestar
from litestar.config.compression import CompressionConfig
from litestar.exceptions import (
    PermissionDeniedException,
    NotFoundException,
    ClientException,
    ValidationException,
)
from litestar.logging import LoggingConfig
from litestar.plugins.htmx import HTMXRequest
from litestar.types import ASGIApp, Scope, HTTPScope

from common import REQUEST_TIMEOUT
from common.installation_checker import InstallationChecker
from common.logger import get_logger, set_logging_config
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.input_output import DataSourceManager
from web.channels import channels_plugin
from web.garbage_collection import RequestGarbageCollectionMiddleware
from web.performance import PerformanceMiddleware
from web.settings import (
    route_handlers,
    template_config,
    middlewares,
    stores,
    exception_handlers,
    listeners,
)

logger = get_logger()

HANDLED_SIGNALS: list[int] = [
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
]
if sys.platform == 'win32':  # pragma: py-not-win32
    HANDLED_SIGNALS.append(signal.SIGBREAK)  # Windows signal 21. Sent by Ctrl+Break.

_PORT_TIMEOUT = 10  # Timeout when looking for a specific port


def launch_browser(url: str) -> None:
    # Set the locale as the function is called in a new thread.
    SharlyChessConfig().load_and_set_env()
    logger.info(f'Opening the welcome page [{url}] in a browser…')
    while True:
        try:
            requests.get(url, timeout=REQUEST_TIMEOUT)
            break
        except requests.RequestException as e:
            msg = f'Web server not started yet ({e.__class__.__name__}), waiting…'
            if isinstance(e, requests.TooManyRedirects) and e.response is not None:
                msg += f' History: {[r.url for r in e.response.history]}'
            logger.info(msg)
            sleep(1)
    open(url, new=2)


class _Server(uvicorn.Server):
    def __init__(
        self, config: uvicorn.Config, on_ready: Callable[[], None] | None
    ) -> None:
        super().__init__(config)
        self.on_ready = on_ready

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        if self.started and self.on_ready:
            self.on_ready()


class ServerEngine:
    app: ClassVar[Litestar | None] = None
    server: ClassVar[uvicorn.Server | None] = None

    def __init__(
        self,
        debug: bool = False,
        profile: bool = False,
        port: int | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        handle_signals: bool = True,
        on_ready: Callable[[], None] | None = None,
    ):
        self.debug = debug
        self.profile = profile
        self.handle_signals = handle_signals
        self.port = port
        # Called once the server accepts connections.
        self.on_ready = on_ready

        # before all the rest, initialize a SharlyChessConfig instance to set the language.
        config = SharlyChessConfig()
        config.load_and_set_env()
        logger.info(
            'Sharly Chess %s - %s - %s',
            config.version,
            config.copyright,
            config.web_url,
        )
        logger.info('Locale: %s', config.locale)
        if not InstallationChecker.check():
            return

        self.loop = self._ensure_loop(loop)

    def _ensure_loop(
        self, loop: asyncio.AbstractEventLoop | None
    ) -> asyncio.AbstractEventLoop:
        if loop is not None:
            return loop
        # Try running loop first (inside an event-loop callback)
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            pass
        # No current running loop -> create & set one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

    def build_app(self, logging_config: dict) -> Litestar:
        """The application the server serves, and the one a test drives
        in-process: both read the routes, middlewares and handlers from
        the same place."""

        def log_http_exception(exc: Exception, scope: Scope) -> None:
            if scope['type'] != 'http':
                return
            if isinstance(exc, PermissionDeniedException):
                prefix = '403 permission denied'
            elif isinstance(exc, NotFoundException):
                prefix = '404 not found'
            elif isinstance(exc, ClientException) and exc.status_code == 400:
                prefix = '400 bad request'
            else:
                return
            http = cast(HTTPScope, scope)
            logger.error(
                '%s: %s %s\n%s',
                prefix,
                http.get('method', '?'),
                http.get('path', '?'),
                exc,
            )

        return Litestar(
            debug=self.debug,
            request_class=HTMXRequest,
            route_handlers=route_handlers,
            exception_handlers=exception_handlers,  # type: ignore[arg-type]
            template_config=template_config,
            # Favor response latency over maximum compression.
            compression_config=CompressionConfig(backend='gzip', gzip_compress_level=3),
            logging_config=LoggingConfig(
                **logging_config,
                # Litestar's default only logs exceptions when debug=True.
                log_exceptions='always',
                disable_stack_trace={
                    400,
                    403,
                    404,
                    ClientException,
                    ValidationException,
                    PermissionDeniedException,
                    NotFoundException,
                },
            ),
            after_exception=[log_http_exception],
            middleware=middlewares,
            stores=stores,
            pdb_on_exception=self.debug,
            plugins=[channels_plugin],
            listeners=listeners,
        )

    async def serve(self) -> None:
        logger.debug('System information:')
        logger.debug(
            ' - Machine/processor: %s/%s', platform.machine(), platform.processor()
        )
        logger.debug(' - Platform: %s', platform.platform())
        logger.debug(' - Architecture: %s', ' '.join(platform.architecture()))
        logger.info('Starting Sharly Chess server, Please wait…')
        sc_config = SharlyChessConfig()
        logger.info(f'Console logging level: {sc_config.console_log_level_str}')

        for data_source in DataSourceManager().objects():
            data_source.on_app_init()

        if self.port:
            for __ in range(_PORT_TIMEOUT):
                if not self.__port_in_use(self.port):
                    sc_config.web_port = self.port
                    break
                logger.debug(f'Port {self.port} already in use (waiting)')
                await asyncio.sleep(1)
            if not sc_config.web_port:
                logger.info(
                    f'Timeout exceeded for port {self.port}, fallback to other ports'
                )
        if not sc_config.web_port:
            for port in sc_config.web_ports:
                if not self.__port_in_use(port):
                    sc_config.web_port = port
                    break
                logger.debug(f'Port {port} already in use')
            if sc_config.web_port is None:
                ports_str = ', '.join(str(port) for port in sc_config.web_ports)
                logger.error(
                    f'All the candidate ports [{ports_str}] are already'
                    f' in use, can not start Sharly Chess server.'
                )
                return

        logger.info(f'Port: {sc_config.web_port}')
        logger.info(f'Local URL: {sc_config.local_url}')

        if sc_config.launch_browser:
            Thread(target=launch_browser, args=(sc_config.local_url,)).start()

        NetworkMonitor.start_monitoring()

        logging_config = set_logging_config(
            console_log_level=sc_config.console_log_level,
        )

        app: Litestar = self.build_app(logging_config)
        self.__class__.app = app
        asgi_app: ASGIApp = RequestGarbageCollectionMiddleware(app)
        if self.profile:
            asgi_app = PerformanceMiddleware(asgi_app)

        config = uvicorn.Config(
            app=asgi_app,
            host=sc_config.web_host,
            port=sc_config.web_port,
            log_config=logging_config,
            timeout_graceful_shutdown=5,
        )
        server = _Server(config, on_ready=self.on_ready)
        self.__class__.server = server

        # The handler each signal already had. Replacing it outright drops
        # whatever the process installed before the server started -- under
        # coverage that is the handler which writes the measurements out, so
        # the whole server process would be measured and never recorded.
        previous_handlers: dict[int, Callable[[int, FrameType | None], object]] = {}

        def handle_exit(sig_: int, frame: FrameType | None) -> None:
            server.should_exit = True
            server.force_exit = True
            previous = previous_handlers.get(sig_)
            if previous is not None:
                previous(sig_, frame)

        # We need to handle signals ourselves in order to gracefully shut down the SSE connections.
        # Calling `serve` doesn't allow us to intercept signals, so we use `_serve` instead.  The only
        # difference is that `serve` captures signals before calling `_serve` internally.

        if self.handle_signals:
            import threading

            if threading.current_thread() is threading.main_thread():
                for sig in HANDLED_SIGNALS:
                    previous = signal.signal(sig, handle_exit)
                    # The interpreter's own Ctrl+C handler raises
                    # KeyboardInterrupt, which is the shutdown this handler
                    # exists to replace: chaining it would undo that.
                    if (
                        callable(previous)
                        and previous is not signal.default_int_handler
                    ):
                        previous_handlers[sig] = previous

        await server._serve()

    @staticmethod
    def __port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
