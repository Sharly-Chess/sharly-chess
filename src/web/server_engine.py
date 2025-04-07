import platform
import socket
from threading import Thread
from time import sleep
from webbrowser import open

import pyodbc  # type: ignore
import requests
import uvicorn
from litestar import Litestar
from litestar.contrib.htmx.request import HTMXRequest
from litestar.logging import LoggingConfig

from pairing.bbp_pairings_installer import BbpPairingsInstaller
from common import DEVEL_ENV, EXPERIMENTAL_FEATURES, REQUEST_TIMEOUT
from common.engine import Engine
from common.i18n import _, set_locale
from common.logger import (
    print_interactive_info,
    print_interactive_error,
    print_interactive_warning,
    LOGGING_CONFIG,
    get_logger,
    set_console_log_level,
)
from common.papi_web_config import PapiWebConfig
from common.network import NetworkMonitor
from database.sqlite.fide.fide_database import FideDatabase
from plugins.manager import plugin_manager
from web.settings import route_handlers, template_config, middlewares, stores

logger = get_logger()


def launch_browser(url: str):
    # Set the locale as the function is called in a new thread.
    set_locale(PapiWebConfig().locale)
    print_interactive_info(
        _('Opening the welcome page [{url}] in a browser...').format(url=url)
    )
    while True:
        try:
            requests.get(url, timeout=REQUEST_TIMEOUT)
            break
        except requests.RequestException as e:
            print_interactive_info(
                _('Web server not started yet ({ex}), waiting...').format(
                    ex=e.__class__.__name__
                )
            )
            sleep(1)
    open(url, new=2)


class ServerEngine(Engine):
    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        if self.updated:
            return
        config = PapiWebConfig()
        set_locale(PapiWebConfig().locale)
        set_console_log_level(config.log_level)

        logger.debug('ODBC drivers found:')
        for driver in pyodbc.drivers():
            logger.debug(' - %s', driver)
        logger.debug('System information:')
        logger.debug(
            ' - Machine/processor: %s/%s', platform.machine(), platform.processor()
        )
        logger.debug(' - Platform: %s', platform.platform())
        logger.debug(' - Architecture: %s', ' '.join(platform.architecture()))
        print_interactive_info(_('Starting Papi-web server, please wait...'))
        papi_web_config: PapiWebConfig = PapiWebConfig()
        print_interactive_info(
            _('Logging level: {log_level}').format(
                log_level=papi_web_config.log_level_str
            )
        )

        FideDatabase().check()

        # Give plugins an opportunity to initialise themselves
        plugin_manager.hook.on_init()
        bbp_pairings = BbpPairingsInstaller()
        if EXPERIMENTAL_FEATURES and not bbp_pairings.is_installed:
            if DEVEL_ENV:
                print_interactive_info(
                    _(
                        'Automatically installing BBP Pairings for developers with PAPI_WEB_EXPERIMENTAL=1.'
                    )
                )
                bbp_pairings.install()
            else:
                raise FileNotFoundError('BBP Pairings not installed.')

        for port in papi_web_config.web_ports:
            if self.__port_in_use(port):
                print_interactive_warning(
                    _('Port [{port}] already in use.').format(port=port)
                )
                continue
            papi_web_config.web_port = port
            break
        if papi_web_config.web_port is None:
            print_interactive_error(
                _(
                    'All the candidate ports [{ports}] are already in use, can not start Papi-web server.'
                ).format(
                    ports=', '.join(str(port) for port in papi_web_config.web_ports)
                )
            )
            return

        print_interactive_info(_('Port: {port}').format(port=papi_web_config.web_port))
        print_interactive_info(
            _('Local URL: {local_url}').format(local_url=papi_web_config.local_url)
        )
        if papi_web_config.lan_url:
            print_interactive_info(
                _('LAN/WAN URL: {lan_url}').format(lan_url=papi_web_config.lan_url)
            )

        if papi_web_config.launch_browser:
            Thread(target=launch_browser, args=(papi_web_config.local_url,)).start()

        NetworkMonitor.start_monitoring()

        logging_config = LOGGING_CONFIG
        logging_config['handlers']['console']['level'] = config.log_level  # type: ignore
        app: Litestar = Litestar(
            debug=True,
            request_class=HTMXRequest,
            route_handlers=route_handlers,
            template_config=template_config,
            logging_config=LoggingConfig(**logging_config),  # type: ignore
            middleware=middlewares,
            stores=stores,
            pdb_on_exception=self.debug,
        )
        uvicorn.run(
            app,
            host=papi_web_config.web_host,
            port=papi_web_config.web_port,
            log_config=logging_config,
        )

    @staticmethod
    def __port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
