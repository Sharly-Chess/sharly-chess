import socket
from logging import Logger
from threading import Thread
from time import sleep
from webbrowser import open

import requests
import uvicorn
from litestar import Litestar
from litestar.contrib.htmx.request import HTMXRequest

from pairing.bbp_pairings_installer import BbpPairingsInstaller
from common import DEVEL_ENV, EXPERIMENTAL_FEATURES
from common.engine import Engine
from common.i18n import _, set_locale
from common.logger import (
    get_logger,
    print_interactive_info,
    print_interactive_error,
)
from common.papi_web_config import PapiWebConfig
from database.sqlite.ffe_database import FfeDatabase
from database.sqlite.fide_database import FideDatabase
from web.settings import route_handlers, template_config, middlewares, stores

logger: Logger = get_logger()


def launch_browser(url: str):
    # Set the locale as the function is called in a new thread.
    set_locale(PapiWebConfig().locale)
    print_interactive_info(
        _('Opening the welcome page [{url}] in a browser...').format(url=url)
    )
    while True:
        try:
            requests.get(url)
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
    def __init__(self):
        super().__init__()
        if self.updated:
            return
        print_interactive_info(_('Starting Papi-web server, please wait...'))
        papi_web_config: PapiWebConfig = PapiWebConfig()
        print_interactive_info(
            _('Logging level: {log_level}').format(
                log_level=papi_web_config.log_level_str
            )
        )
        print_interactive_info(_('Port: {port}').format(port=papi_web_config.web_port))
        print_interactive_info(
            _('Local URL: {local_url}').format(local_url=papi_web_config.local_url)
        )
        if papi_web_config.lan_url:
            print_interactive_info(
                _('LAN/WAN URL: {lan_url}').format(lan_url=papi_web_config.lan_url)
            )
        if not FideDatabase().check():
            print_interactive_error(_('Error while updating the FIDE database.'))
        if not FfeDatabase().check():
            print_interactive_error(_('Error while updating the FFE database.'))
        if EXPERIMENTAL_FEATURES and not BbpPairingsInstaller.is_installed:
            if DEVEL_ENV:
                print_interactive_info(_('Automatically installing BBP Pairings for developers with PAPI_WEB_EXPERIMENTAL=1.'))
                BbpPairingsInstaller().install()
            else:
                raise FileNotFoundError('BBP Pairings not installed.')
        if self.__port_in_use(papi_web_config.web_port):
            print_interactive_error(
                _(
                    'Port [{port}] already in use, can not start Papi-web server.'
                ).format(port=papi_web_config.web_port)
            )
            return
        if papi_web_config.web_launch_browser:
            Thread(target=launch_browser, args=(papi_web_config.local_url,)).start()
        app: Litestar = Litestar(
            debug=True,
            request_class=HTMXRequest,
            route_handlers=route_handlers,
            template_config=template_config,
            middleware=middlewares,
            stores=stores,
        )
        # This code is intended to check the uniformity of the paths and names used for the application URLs
        # url_map: defaultdict[str, list[str]] = defaultdict(list[str])
        # name_map: defaultdict[str, list[str]] = defaultdict(list[str])
        # for route in app.routes:
        #     for handler in route.route_handlers:
        #         if handler.name:
        #             url_map[handler.name].append(route.path)
        #             name_map[route.path].append(handler.name)
        # for name in sorted(url_map.keys()):
        #     logger.warning(f'{name}: {url_map[name]}')
        # for path in sorted(name_map.keys()):
        #     logger.warning(f'{path}: {name_map[path]}')
        uvicorn.run(
            app,
            host=papi_web_config.web_host,
            port=papi_web_config.web_port,
            log_level='info',
        )

    @staticmethod
    def __port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
