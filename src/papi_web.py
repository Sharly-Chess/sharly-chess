try:
    import argparse
    import os
    import traceback
    from typing import TYPE_CHECKING

    # undocumented feature to start from a different folder and work with different configurations
    # Has to be executed before plugin_manager to avoid initializing from the wrong path
    path_parser = argparse.ArgumentParser(add_help=False)
    path_parser.add_argument('--path', default='.')
    args, remaining_args = path_parser.parse_known_args()
    os.chdir(args.path)

    from common import DEVEL_ENV, enable_experimental_features
    from common.i18n import _
    from common.logger import (
        get_logger,
        print_interactive_warning,
    )

    logger = get_logger()

    from plugins.manager import plugin_manager  # Noqa: E402
    from web.server_engine import ServerEngine  # Noqa: E402

    if TYPE_CHECKING:
        from plugins.utils import PluginEngineArgument

    parser = argparse.ArgumentParser(parents=[path_parser])
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
    args = parser.parse_args(remaining_args)

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
    print('An error occurred, press Enter to end.')
    input()
