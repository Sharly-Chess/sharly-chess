import asyncio
import platform
import signal
import socket
from pathlib import Path
import sys
from threading import Thread
from time import sleep
from types import FrameType
from webbrowser import open

import pyodbc  # type: ignore
import requests
import uvicorn
from litestar import Litestar
from litestar.plugins.htmx import HTMXRequest
from litestar.logging import LoggingConfig

from common import REQUEST_TIMEOUT, LOG_FILE
from common.engine import Engine
from common.i18n import _, set_locale
from common.logger import (
    print_interactive_info,
    print_interactive_error,
    print_interactive_warning,
    get_logger,
    set_logging_config,
)
from common.sharly_chess_config import SharlyChessConfig
from common.network import NetworkMonitor
from database.sqlite.fide.fide_database import FideDatabase
from plugins.manager import plugin_manager
from web.settings import (
    route_handlers,
    template_config,
    middlewares,
    stores,
    exception_handlers,
)
from web.channels import channels_plugin

logger = get_logger()

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)
if sys.platform == 'win32':  # pragma: py-not-win32
    HANDLED_SIGNALS += (signal.SIGBREAK,)  # Windows signal 21. Sent by Ctrl+Break.


def launch_browser(url: str):
    # Set the locale as the function is called in a new thread.
    set_locale(SharlyChessConfig().locale)
    print_interactive_info(
        _('Opening the welcome page [{url}] in a browser…').format(url=url)
    )
    while True:
        try:
            requests.get(url, timeout=REQUEST_TIMEOUT)
            break
        except requests.RequestException as e:
            print_interactive_info(
                _('Web server not started yet ({ex}), waiting…').format(
                    ex=e.__class__.__name__
                )
            )
            sleep(1)
    open(url, new=2)


class ServerEngine(Engine):
    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        if self.error:
            return

        logger.debug('ODBC drivers found:')
        for driver in pyodbc.drivers():
            logger.debug(' - %s', driver)
        logger.debug('System information:')
        logger.debug(
            ' - Machine/processor: %s/%s', platform.machine(), platform.processor()
        )
        logger.debug(' - Platform: %s', platform.platform())
        logger.debug(' - Architecture: %s', ' '.join(platform.architecture()))
        print_interactive_info(_('Starting Sharly Chess server, Please wait…'))
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        print_interactive_info(
            _('Console logging level: {console_log_level}').format(
                console_log_level=sharly_chess_config.console_log_level_str
            )
        )

        FideDatabase().check()

        # Give plugins an opportunity to initialise themselves
        plugin_manager.hook.on_init()

        for port in sharly_chess_config.web_ports:
            if self.__port_in_use(port):
                print_interactive_warning(
                    _('Port [{port}] already in use.').format(port=port)
                )
                continue
            sharly_chess_config.web_port = port
            break
        if sharly_chess_config.web_port is None:
            print_interactive_error(
                _(
                    'All the candidate ports [{ports}] are already in use, can not start Sharly Chess server.'
                ).format(
                    ports=', '.join(str(port) for port in sharly_chess_config.web_ports)
                )
            )
            return

        print_interactive_info(
            _('Port: {port}').format(port=sharly_chess_config.web_port)
        )
        print_interactive_info(
            _('Local URL: {local_url}').format(local_url=sharly_chess_config.local_url)
        )
        if sharly_chess_config.lan_url:
            print_interactive_info(
                _('LAN/WAN URL: {lan_url}').format(lan_url=sharly_chess_config.lan_url)
            )

        if sharly_chess_config.launch_browser:
            Thread(target=launch_browser, args=(sharly_chess_config.local_url,)).start()

        NetworkMonitor.start_monitoring()

        logging_config = set_logging_config(
            console_log_level=SharlyChessConfig().console_log_level
        )

        app: Litestar = Litestar(
            debug=True,
            request_class=HTMXRequest,
            route_handlers=route_handlers,
            exception_handlers=exception_handlers,  # type: ignore
            template_config=template_config,
            logging_config=LoggingConfig(**logging_config),  # type: ignore
            middleware=middlewares,
            stores=stores,
            pdb_on_exception=self.debug,
            plugins=[channels_plugin],
        )

        config = uvicorn.Config(
            app=app,
            host=sharly_chess_config.web_host,
            port=sharly_chess_config.web_port,
            log_config=logging_config,
            timeout_graceful_shutdown=5,
        )
        server = uvicorn.Server(config)

        def handle_exit(sig: int, frame: FrameType | None) -> None:
            server.should_exit = True
            server.force_exit = True
            # Close the SSE connections gracefully
            if channels_plugin and channels_plugin._pub_queue is not None:
                channels_plugin.publish(
                    {'event': 'server_shutdown', 'data': ''}, ['sse']
                )

        # We need to handle signals ourselves in order to gracefully shut down the SSE connections.
        # Calling `serve` doesn't allow us to intercept signals, so we use `_serve` instead.  The only
        # difference is that `serve` captures signals before calling `_serve` internally.

        for sig in HANDLED_SIGNALS:
            signal.signal(sig, handle_exit)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(server._serve())

    @property
    def log_file_path(self) -> Path:
        return LOG_FILE

    @staticmethod
    def __port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
