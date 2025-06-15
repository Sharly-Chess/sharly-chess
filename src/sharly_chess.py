try:
    import argparse
    import traceback
    from typing import TYPE_CHECKING

    from utils.scripts import init_script

    arguments = init_script()

    from common import DEVEL_ENV, enable_experimental_features
    from common.i18n import _
    from common.logger import (
        get_logger,
        print_interactive_warning,
    )
    from plugins.manager import plugin_manager
    from web.server_engine import ServerEngine

    if TYPE_CHECKING:
        from plugins.utils import PluginEngineArgument

    logger = get_logger()

    parser = argparse.ArgumentParser()
    parser.add_argument('--experimental', action='store_true')
    parser.add_argument('--server', action='store_true')
    engine_argument_names: list[str] = []
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
    args = parser.parse_args(arguments)

    enable_experimental_features(bool(args.experimental))
    if args.server:
        print_interactive_warning(_('Argument --server is deprecated, ignored.'))
    try:
        plugin_engine_argument: 'PluginEngineArgument | None' = None
        for engine_argument in plugin_engine_arguments:
            if getattr(args, engine_argument.name, False):
                plugin_engine_argument = engine_argument
                engine_argument.init_engine()
                break
        if plugin_engine_argument is None:
            se: ServerEngine = ServerEngine(debug=(DEVEL_ENV and args.debug))
    except KeyboardInterrupt:
        pass
except Exception:
    message = traceback.format_exc()
    try:
        from common.logger import get_logger

        logger = get_logger()
        logger.error(message)
    except Exception:
        print(message)
    print('An error occurred.')
from contextlib import suppress

with suppress(UnicodeDecodeError):
    input('Press Enter to end.')
