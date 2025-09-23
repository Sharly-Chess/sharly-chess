import platform
import sys

if platform.system() == 'Windows':
    # Windows marks the downloaded files as unsure and blocks their usage.
    # On the first run, all the files of the distribution are unmarked.
    from pathlib import Path

    base_dir: Path = Path(sys.argv[0]).resolve().parent
    tracer: Path = base_dir / '_internal' / '.unblock_files'
    if tracer.exists():
        import os

        print(f'Unblocking files in : {base_dir}')
        for root_, __, files in os.walk(base_dir):
            for name in files:
                path = os.path.join(root_, name)
                # Remove Zone.Identifier ADS if it exists
                ads_path = path + ':Zone.Identifier'
                try:
                    os.remove(ads_path)
                    print(f'Unblocked: {path}')
                except FileNotFoundError:
                    pass  # not blocked or already unblocked
                except Exception as e:
                    print(f'Failed to unblock {path}: {e}')
        # Remove not to run twice
        tracer.unlink()

if platform.system() == 'Darwin':
    # Prevent MacOS from sleeping the windowed app when it's in the background
    from rubicon.objc import ObjCClass

    NSProcessInfo = ObjCClass('NSProcessInfo')
    NSProcessInfo.processInfo.beginActivityWithOptions_reason_(
        0x00FFFFFF,  # NSActivityUserInitiated | NSActivityLatencyCritical
        'Prevent App Nap',
    )

try:
    import argparse
    import asyncio
    import sys

    from utils.scripts import init_script

    arguments = init_script()

    from common import DEVEL_ENV, TEST_ENV
    from common.i18n import _
    from common.logger import (
        get_logger,
        print_interactive_warning,
    )
    from gui.server_gui_toga import SharlyChessServerToga
    from web.server_engine import ServerEngine

    logger = get_logger()

    parser = argparse.ArgumentParser()
    parser.add_argument('--server', action='store_true')

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        help='force the web port tu use',
    )
    if DEVEL_ENV:
        parser.add_argument(
            '-d',
            '--debug',
            help='on the webserver, if there is an uncaught exception, drop to PDB',
            action='store_true',
        )
    if DEVEL_ENV or TEST_ENV:
        parser.add_argument(
            '--cli',
            action='store_true',
            help='Force console/CLI mode (default is GUI for bundled apps)',
        )
    args = parser.parse_args(arguments)

    if args.server:
        print_interactive_warning(_('Argument --server is deprecated, ignored.'))

    # Check if GUI mode should be used
    if not TEST_ENV and not (DEVEL_ENV and args.cli):
        # Create and run the Toga app - this should block until the app exits
        app = SharlyChessServerToga()
        app.main_loop()
        sys.exit(0)

    # Original console mode
    try:
        se: ServerEngine = ServerEngine(debug=args.debug, port=args.port or None)
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
