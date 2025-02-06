import argparse
import os
import sys
from logging import Logger

from chessevent.chessevent_engine import ChessEventEngine
from common.i18n import _
from common.logger import get_logger
from ffe.ffe_engine import FFEEngine
from web.server_engine import ServerEngine

try:
    logger: Logger = get_logger()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--server", help="start the web server", action="store_true"
    )
    parser.add_argument(
        "-f", "--ffe", help="run the FFE utilities", action="store_true"
    )
    parser.add_argument(
        "-c",
        "--chessevent",
        help="download Papi files from Chess Event",
        action="store_true",
    )
    # undocumented feature to start from a different folder and work with different configurations
    parser.add_argument("--path", default=".")
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
        logger.error(
            _(
                "This program should not be launched directly, use the scripts server.bat, ffe.bat and chessevent.bat."
            )
        )
except KeyboardInterrupt:
    pass
