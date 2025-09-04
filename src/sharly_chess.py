import asyncio

from common import TEST_ENV

gui_success = False

try:
    import argparse
    import traceback
    from typing import TYPE_CHECKING

    from utils.scripts import init_script

    arguments = init_script()

    from common import DEVEL_ENV
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
    parser.add_argument('--server', action='store_true')
    parser.add_argument(
        '--cli',
        action='store_true',
        help='Force console/CLI mode (default is GUI for bundled apps)',
    )
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        help='force the web port tu use',
    )
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

    if args.server:
        print_interactive_warning(_('Argument --server is deprecated, ignored.'))

    # Check if any plugin engine argument was passed
    has_plugin_engine_arg = any(
        getattr(args, arg.name)  # each was added as store_true
        for arg in plugin_engine_arguments
    )

    # Check if GUI mode should be used
    if not args.cli and not has_plugin_engine_arg and not TEST_ENV:
        try:
            from gui.server_gui_toga import SharlyChessServerToga

            # Create and run the Toga app - this should block until the app exits
            app = SharlyChessServerToga()

            try:
                app.main_loop()
            except Exception as e:
                error_msg = f'main_loop() failed with exception: {e}'
                print(error_msg)

            gui_success = True
            exit(0)
        except Exception as e:
            error_msg = f'GUI initialization failed: {e}'
            print(error_msg)
            import traceback

            traceback.print_exc()

            raise e

    # Original console mode
    try:
        plugin_engine_argument: 'PluginEngineArgument | None' = None
        for engine_argument in plugin_engine_arguments:
            if getattr(args, engine_argument.name, False):
                plugin_engine_argument = engine_argument
                engine_argument.init_engine()
                break
        if plugin_engine_argument is None:
            se: ServerEngine = ServerEngine(
                debug=(DEVEL_ENV and args.debug), port=args.port or None
            )
            asyncio.run(se.serve())
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
