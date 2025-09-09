import platform
from common import DEVEL_ENV, TEST_ENV, BASE_DIR

if not DEVEL_ENV and not TEST_ENV and platform.system() == 'Windows':
    # Windows marks the downloaded files as unsure and blocks their usage.
    # On the first run, all the files of the distribution are unmarked.
    from pathlib import Path

    tracer: Path = BASE_DIR / '_internal' / '.unblock_files'
    if tracer.exists():
        import os

        print(f'Unblocking files in : {BASE_DIR}')
        for root, _, files in os.walk(BASE_DIR):
            for name in files:
                path = os.path.join(root, name)
                # Remove Zone.Identifier ADS if it exists
                ads_path = path + ':Zone.Identifier'
                try:
                    os.remove(ads_path)
                    print(f'Unblocked: {path}')
                except FileNotFoundError:
                    pass  # Already unblocked
                except Exception as e:
                    print(f'Failed to unblock {path}: {e}')
        # Remove not to run twice
        tracer.unlink()

try:
    import argparse
    import asyncio
    from typing import TYPE_CHECKING
    import sys

    from utils.scripts import init_script

    arguments = init_script()

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
        sys.exit(0)

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
    import platform
    import sys
    import traceback

    message = traceback.format_exc()
    try:
        from common.logger import get_logger

        logger = get_logger()
        logger.error(message)
    except Exception:
        pass

    test_env = os.getenv('TEST_ENV') == 'true'
    if test_env:
        sys.exit(1)

    title = 'Sharly Chess startup error'

    match platform.system():
        case 'Windows':
            import tkinter
            from tkinter import messagebox

            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror('Sharly Chess startup error', message)
            root.destroy()

        case 'Darwin':
            import subprocess

            message = message.replace('"', '\\"')
            script = (
                f'display alert "{title}" message "{message}" '
                'as critical buttons {"OK"}'
            )
            subprocess.run(['osascript', '-e', script], check=True)
