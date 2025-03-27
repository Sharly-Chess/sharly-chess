import argparse
import os
import sys
from logging import Logger
from typing import TYPE_CHECKING

from common import DEVEL_ENV
from common.i18n import _
from common.logger import get_logger

if TYPE_CHECKING:
    from plugins.utils import PluginEngineArgument


# undocumented feature to start from a different folder and work with different configurations
# Has to be executed before plugin_manager to avoid initializing from the wrong path
path_parser = argparse.ArgumentParser(add_help=False)
path_parser.add_argument('--path', default='.')
args, remaining_args = path_parser.parse_known_args()
os.chdir(args.path)

from plugins.manager import plugin_manager  # Noqa: E402
from web.server_engine import ServerEngine  # Noqa: E402

logger: Logger = get_logger()

parser = argparse.ArgumentParser(parents=[path_parser])
parser.add_argument('-s', '--server', help='start the web server', action='store_true')
engine_argument_names: list[str] = ['server']
plugin_engine_arguments: list['PluginEngineArgument'] = (
    plugin_manager.hook.get_engine_argument()
)
for argument in plugin_engine_arguments:
    parser.add_argument(
        f'-{argument.flag}',
        f'--{argument.name}',
        help=argument.help,
        action='store_true',
    )
    engine_argument_names.append(argument.name)
if DEVEL_ENV:
    parser.add_argument(
        '-d',
        '--debug',
        help='on the webserver, if there is an uncaught exception, drop to PDB',
        action='store_true',
    )
args = parser.parse_args(remaining_args)

if not any(getattr(args, name, False) for name in engine_argument_names):
    parser.print_help(sys.stderr)
    logger.error(
        _(
            'This program should not be launched directly, '
            'use the scripts server.bat, ffe.bat and chessevent.bat.'
        )
    )
    sys.exit(1)
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
