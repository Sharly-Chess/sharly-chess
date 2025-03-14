import argparse
import os
import sys
from logging import Logger

from common import DEVEL_ENV
from common.i18n import _
from common.logger import get_logger
from plugins.manager import plugin_manager
from plugins.utils import PluginEngineArgument
from web.server_engine import ServerEngine

logger: Logger = get_logger()


plugin_engine_arguments: list[PluginEngineArgument] = (
    plugin_manager.hook.get_engine_argument()
)
parser = argparse.ArgumentParser()
parser.add_argument(
    '-s', '--server', help='start the web server', action='store_true'
)
engine_argument_names: list[str] = ['server']
for argument in plugin_engine_arguments:
    parser.add_argument(
        f'-{argument.flag}',
        f'--{argument.name}',
        help=argument.help,
        action='store_true',
    )
    engine_argument_names.append(argument.name)
# undocumented feature to start from a different folder and work with different configurations
parser.add_argument('--path', default='.')
if DEVEL_ENV:
    parser.add_argument(
        '-d',
        '--debug',
        help='on the webserver, if there is an uncaught exception, drop to PDB',
        action='store_true',
    )
args = parser.parse_args()

if not any(getattr(args, name, False) for name in engine_argument_names):
    parser.print_help(sys.stderr)
    logger.error(
        _(
            'This program should not be launched directly, '
            'use the scripts server.bat, ffe.bat and chessevent.bat.'
        )
    )
    sys.exit(1)
os.chdir(args.path)
try:
    if args.server:
        se: ServerEngine = ServerEngine(debug=(DEVEL_ENV and args.debug))
    else:
        for engine_argument in plugin_engine_arguments:
            if getattr(args, engine_argument.name, False):
                pe = engine_argument.init_engine()
                break
except KeyboardInterrupt:
    pass
