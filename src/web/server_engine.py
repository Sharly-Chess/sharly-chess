import socket
from logging import Logger
from threading import Thread
from time import sleep
from webbrowser import open

import requests
import uvicorn
from litestar import Litestar
from litestar.contrib.htmx.request import HTMXRequest

from common.engine import Engine
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from web.settings import route_handlers, template_config, middlewares

logger: Logger = get_logger()


def launch_browser(url: str):
    logger.info(f'Opening the welcome page [{url}] in a browser...')
    while True:
        try:
            requests.get(url)
            break
        except requests.RequestException as e:
            logger.debug(f'Web server not started yet ({e.__class__.__name__}), waiting...')
            sleep(1)
    open(url, new=2)


class ServerEngine(Engine):
    def __init__(self):
        logger.info(f'Starting Papi-web server, please wait...')
        super().__init__()
        if self.updated:
            return
        papi_web_config: PapiWebConfig = PapiWebConfig()
        logger.info(f'log: {papi_web_config.log_level_str}')
        logger.info(f'port: {papi_web_config.web_port}')
        logger.info(f'local URL: {papi_web_config.local_url}')
        if papi_web_config.lan_url:
            logger.info(f'LAN/WAN URL: {papi_web_config.lan_url}')
        if self.__port_in_use(papi_web_config.web_port):
            logger.error(f'Port [{papi_web_config.web_port}] already in use, can not start Papi-web server')
            return
        if papi_web_config.web_launch_browser:
            Thread(target=launch_browser, args=(papi_web_config.local_url, )).start()
        app: Litestar = Litestar(
            debug=True,
            request_class=HTMXRequest,
            route_handlers=route_handlers,
            template_config=template_config,
            middleware=middlewares,
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
        uvicorn.run(app, host=papi_web_config.web_host, port=papi_web_config.web_port, log_level='info', )

    @staticmethod
    def __port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
