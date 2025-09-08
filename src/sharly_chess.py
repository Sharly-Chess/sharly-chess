try:
    import argparse
    import asyncio
    from typing import TYPE_CHECKING

    from utils.scripts import init_script

    arguments = init_script()

    from common import DEVEL_ENV, TEST_ENV
    from common.i18n import _
    from common.logger import (
        get_logger,
        print_interactive_warning,
    )
    from gui.server_gui_toga import SharlyChessServerToga
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
        # Create and run the Toga app - this should block until the app exits
        app = SharlyChessServerToga()
        app.main_loop()
        exit(0)

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
    import os
    import sys
    import tkinter
    from tkinter import messagebox
    import traceback

    message = traceback.format_exc()
    error_logged = False
    try:
        from common.logger import get_logger

        logger = get_logger()
        logger.error(message)
        error_logged = True
    except Exception:
        pass

    test_env = os.getenv('TEST_ENV') == 'true'
    devel_env = not getattr(sys, 'frozen', False)

    if test_env:
        sys.exit(1)

    root = tkinter.Tk()
    root.withdraw()

    if error_logged and not devel_env:
        message = 'Consult the logs for more details.'
    elif not error_logged:
        message = 'Error could not be logged:\n\n' + message
    messagebox.showerror('Sharly Chess startup error', message)
    root.destroy()
