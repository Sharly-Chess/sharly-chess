import asyncio
from contextlib import suppress

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
    parser.add_argument('--gui', action='store_true', help='Launch in GUI mode')
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

    # Check if GUI mode is requested
    if args.gui:
        # Use the Toga GUI exclusively; do not fall back to Tkinter
        try:
            from gui.server_gui_toga import SharlyChessServerToga

            app = SharlyChessServerToga()
            app.main_loop()
            gui_success = True
        except Exception as e:
            print(f'GUI initialization failed: {e}')
            print('Falling back to console mode...')
            args.gui = False

        if gui_success:
            # GUI ran successfully, exit
            pass
        else:
            # GUI failed, continue to console mode
            args.gui = False

    if not args.gui:
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

enter_to_end = True
try:
    from common import TEST_ENV

    enter_to_end = not TEST_ENV and not gui_success
except Exception:
    enter_to_end = not gui_success

if enter_to_end:
    with suppress(UnicodeDecodeError):
        input('Press Enter to end.')
