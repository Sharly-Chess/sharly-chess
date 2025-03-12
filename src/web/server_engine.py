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
    print_interactive_error, print_interactive_warning,
)
from common.papi_web_config import PapiWebConfig
from database.sqlite.fide.fide_database import FideDatabase

from plugins.manager import plugin_manager
from plugins.registration import register_plugins

register_plugins()
        
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
    def __init__(self, debug: bool=False):
        super().__init__()
        self.debug = debug
        if self.updated:
            return
        
        print_interactive_info(_('Starting Papi-web server, please wait...'))
        papi_web_config: PapiWebConfig = PapiWebConfig()
        print_interactive_info(
            _('Logging level: {log_level}').format(
                log_level=papi_web_config.log_level_str
            )
        )

        if not FideDatabase().check():
            print_interactive_error(_('Error while updating the FIDE database.'))

        # Give plugins an opportunity to initialise themselves
        plugin_manager.hook.on_init()

        if EXPERIMENTAL_FEATURES and not BbpPairingsInstaller.is_installed:
            if DEVEL_ENV:
                print_interactive_info(_('Automatically installing BBP Pairings for developers with PAPI_WEB_EXPERIMENTAL=1.'))
                BbpPairingsInstaller().install()
            else:
                raise FileNotFoundError('BBP Pairings not installed.')

        for port in papi_web_config.web_ports:
            if self.__port_in_use(port):
                print_interactive_warning(
                    _(
                        'Port [{port}] already in use.'
                    ).format(port=port)
                )
                continue
            papi_web_config.web_port = port
            break
        if papi_web_config.web_port is None:
            print_interactive_error(
                _(
                    'All the candidate ports [{ports}] are already in use, can not start Papi-web server.'
                ).format(ports=', '.join(str(port) for port in papi_web_config.web_ports))
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
        app: Litestar = Litestar(
            debug=True,
            request_class=HTMXRequest,
            route_handlers=route_handlers,
            template_config=template_config,
            middleware=middlewares,
            stores=stores,
            pdb_on_exception=self.debug,
        )
        # This code is intended to check the uniformity of the paths and names used for the application URLs
        #uris: dict[str, dict[str, str]] = {}
        #for route in app.routes:
        #    for handler in route.route_handlers:
        #        if handler.name:
        #            paths: list[str]
        #            match route.path:
        #                case '/admin/event/{event_uniq_id:str}/{admin_event_tab:str}':
        #                    paths = [
        #                        route.path.replace('{admin_event_tab:str}', tab) for tab in [
        #                            'config', 'tournaments', 'players', 'screens', 'families', 'rotators', 'timers',
        #                        ]
        #                    ]
        #                case '/admin/{admin_tab:str}':
        #                    paths = [
        #                        route.path.replace('{admin_tab:str}', tab) for tab in [
        #                            'config', 'current_events', 'coming_events', 'passed_events', 'archives',
        #                        ]
        #                    ]
        #                case'/user/event/{event_uniq_id:str}/{user_event_tab:str}':
        #                    paths = [
        #                        route.path.replace('{user_event_tab:str}', tab) for tab in [
        #                            'input', 'boards', 'players', 'results', 'ranking', 'image', 'rotators',
        #                        ]
        #                    ]
        #                case '/user/{user_tab:str}':
        #                    paths = [
        #                        route.path.replace('{user_tab:str}', tab) for tab in [
        #                            'current_events', 'coming_events', 'passed_events',
        #                        ]
        #                    ]
        #                case _:
        #                    paths = [route.path, ]
        #            entry_point: str = handler.handler_id.split(":", maxsplit=1)[0]
        #            name = handler.name
        #            http_method = list(handler.http_methods)[0]
        #            controller_name = '.'.join(entry_point.split('.')[2:-1])
        #            controller_method = entry_point.split('.')[-1]
        #            uris |= {
        #                path: {
        #                    'name': name,
        #                    'http_method': http_method,
        #                    'controller_name': controller_name,
        #                    'controller_method': controller_method,
        #                }
        #                for path in paths
        #            }
        #logger.info('| Method URI<br>Name | Controller method (``web.controllers.``) | |')
        #logger.info('|-|-|-|')
        #for path in sorted(uris.keys()):
        #    uri: dict[str, str] = uris[path]
        #    logger.info(f'| ``{uri["http_method"]} {path}``<br/>``{uri["name"]}`` | ``{uri["controller_name"]}``<br/>``{uri["controller_method"]}()`` | |')
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
