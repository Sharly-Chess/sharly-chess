import argparse
import sys
from logging import Logger
import os

from chessevent.chessevent_engine import ChessEventEngine
from common.papi_web_config import PapiWebConfig
from ffe.ffe_engine import FFEEngine
from web.server_engine import ServerEngine
from common.logger import get_logger

try:
    logger: Logger = get_logger()

    logger.info(f'Papi-web {PapiWebConfig.version} Copyright {PapiWebConfig.copyright}')
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--server', help='start the web server', action='store_true')
    parser.add_argument('-f', '--ffe', help='run the FFE utilities', action='store_true')
    parser.add_argument('-c', '--chessevent', help='download Papi files from Chess Event', action='store_true')
    # undocumented feature to start from a different folder and work with different configurations
    parser.add_argument('--path', default='.')
    args = parser.parse_args()
    os.chdir(args.path)

    if args.server:
        se: ServerEngine = ServerEngine()
    elif args.ffe:
        fe: FFEEngine = FFEEngine()
    elif args.chessevent:
        ce: ChessEventEngine = ChessEventEngine()
    else:
        parser.print_help(sys.stderr)
        logger.error('Ce programme ne devrait pas être lancé directement, utiliser les scripts '
                     'server.bat, ffe.bat et chessevent.bat.')
except KeyboardInterrupt:
    pass
